import os
import json
import base64
import audioop
import asyncio
from fastapi import FastAPI, Request, WebSocket, Response
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.frames.frames import AudioRawFrame, InputAudioRawFrame, OutputAudioRawFrame, TextFrame, LLMMessagesAppendFrame

from agent import SYSTEM_PROMPT
from exotel_handler import initiate_outbound_call

load_dotenv()

app = FastAPI()

RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost:8000")
if RAILWAY_URL.startswith("https://"):
    RAILWAY_URL = RAILWAY_URL.replace("https://", "")
elif RAILWAY_URL.startswith("http://"):
    RAILWAY_URL = RAILWAY_URL.replace("http://", "")

class ExotelFrameSerializer(FrameSerializer):
    def __init__(self, stream_sid: str):
        self.stream_sid = stream_sid

    async def serialize(self, frame) -> str | bytes:
        if isinstance(frame, AudioRawFrame):
            try:
                # Sarvam TTS is typically 16kHz or Pipecat normalizes to 16kHz
                # Convert PCM 16kHz down to 8kHz
                pcm_8k, _ = audioop.ratecv(frame.audio, 2, 1, frame.sample_rate, 8000, None)
                # Convert PCM to ulaw
                ulaw_audio = audioop.lin2ulaw(pcm_8k, 2)
                payload = base64.b64encode(ulaw_audio).decode("utf-8")
                msg = {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": payload}
                }
                return json.dumps(msg)
            except Exception as e:
                print(f"Serialize error: {e}")
                return ""
        return ""

    async def deserialize(self, data: str | bytes):
        if isinstance(data, str):
            try:
                msg = json.loads(data)
                if msg.get("event") == "start":
                    self.stream_sid = msg.get("start", {}).get("streamSid", self.stream_sid)
                elif msg.get("event") == "media":
                    payload = msg["media"]["payload"]
                    ulaw_audio = base64.b64decode(payload)
                    # Convert ulaw 8kHz to PCM 8kHz
                    pcm_8k = audioop.ulaw2lin(ulaw_audio, 2)
                    # Convert 8kHz to 16kHz PCM for Sarvam
                    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
                    return InputAudioRawFrame(audio=pcm_16k, sample_rate=16000, num_channels=1)
            except Exception as e:
                print(f"Deserialize error: {e}")
        return None

@app.get("/health")
async def health():
    return {"status": "running"}

@app.post("/make-call")
async def make_call(request: Request):
    data = await request.json()
    phone = data.get("phone")
    name = data.get("name", "Business")
    
    if not phone:
        return JSONResponse({"error": "Phone number is required"}, status_code=400)
    
    try:
        railway_url_https = f"https://{RAILWAY_URL}"
        res = initiate_outbound_call(phone, railway_url_https)
        return {"status": "success", "call_details": res}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/call-handler")
async def call_handler(request: Request):
    # Standard Exotel/Twilio TwiML to start WebSocket stream
    wss_url = f"wss://{RAILWAY_URL}/audio-stream"
    xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{wss_url}" />
    </Connect>
</Response>"""
    return Response(content=xml_data, media_type="application/xml")

@app.post("/call-status")
async def call_status(request: Request):
    form_data = await request.form()
    print("Call status update:", form_data)
    return {"status": "ok"}

@app.websocket("/audio-stream")
async def audio_stream(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection established")

    try:
        serializer = ExotelFrameSerializer(stream_sid="")
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_out_enabled=True,
                add_wav_header=False,
                audio_in_enabled=True,
                serializer=serializer
            )
        )

        stt = SarvamSTTService(
            api_key=os.getenv("SARVAM_API_KEY")
        )
        
        llm = GoogleLLMService(
            api_key=os.getenv("GEMINI_API_KEY"),
            settings=GoogleLLMService.Settings(
                model="gemini-2.5-flash"
            )
        )
        
        tts = SarvamTTSService(
            api_key=os.getenv("SARVAM_API_KEY")
        )

        # Context aggregator
        from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregator, LLMAssistantAggregator
        from pipecat.processors.aggregators.llm_context import LLMContext
        
        context = LLMContext(
            messages=[{"role": "system", "content": SYSTEM_PROMPT}]
        )
        context_aggregator_user = LLMUserAggregator(context)
        context_aggregator_assistant = LLMAssistantAggregator(context)

        # VAD
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.processors.audio.vad_processor import VADProcessor
        vad_analyzer = SileroVADAnalyzer()
        vad = VADProcessor(vad_analyzer=vad_analyzer)

        # Create Pipeline
        pipeline = Pipeline([
            transport.input(),
            vad,
            stt,
            context_aggregator_user,
            llm,
            tts,
            transport.output(),
            context_aggregator_assistant
        ])

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True
            )
        )

        # Initial prompt to speak immediately on connection
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            # Send initial frame to LLM to kickstart
            await task.queue_frames([LLMMessagesAppendFrame([{"role": "user", "content": "Hello!"}], run_llm=True)])

        runner = PipelineRunner()
        await runner.run(task)
        print("Pipeline finished successfully")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print("WebSocket connection closed")
        if not websocket.client_state.name == "DISCONNECTED":
            try:
                await websocket.close()
            except RuntimeError:
                pass
