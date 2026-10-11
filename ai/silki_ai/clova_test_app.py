"""Standalone browser microphone test for CLOVA Speech streaming."""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from silki_ai.clova import ClovaEventKind, ClovaStreamingClient, load_clova_keywords
from silki_ai.config import Settings

app = FastAPI(title="Silki CLOVA Speech Check", version="0.1.0")
TRANSCRIPT_LOG_PATH = Path("data/clova_transcripts.jsonl")

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Silki CLOVA Check</title><style>
:root{font-family:Georgia,"Noto Serif KR",serif;color:#17231f;background:#f4f5ef}*{box-sizing:border-box}body{margin:0;min-height:100vh;padding:24px;display:grid;place-items:center;background:repeating-linear-gradient(135deg,#f4f5ef 0 18px,#edf0e8 18px 19px)}main{width:min(100%,720px);border-top:6px solid #e8603c;padding-top:38px}h1{margin:0;font-size:42px;font-weight:600}.subtitle,#status,h2,button{font-family:"Noto Sans KR",sans-serif}.subtitle{color:#526159;margin:10px 0 32px}.controls{display:flex;gap:10px;flex-wrap:wrap}button{min-height:48px;padding:0 22px;border:1px solid #17231f;border-radius:4px;background:#17231f;color:white;font-size:16px;cursor:pointer}button.secondary{background:transparent;color:#17231f}button:disabled{opacity:.45;cursor:not-allowed}#status{min-height:24px;margin:18px 0 28px;color:#c94729;font-weight:600;font-size:14px}section{border-top:1px solid #b7c0b8;padding:18px 0 26px}h2{margin:0 0 10px;color:#526159;font-size:14px}p{margin:0;min-height:32px;font-size:24px;line-height:1.5;word-break:keep-all}@media(max-width:560px){h1{font-size:34px}p{font-size:21px}}</style></head>
<body><main><h1>Silki CLOVA Check</h1><p class="subtitle">마이크 오디오를 네이버 CLOVA Speech 스트리밍으로 직접 전송합니다.</p>
<div class="controls"><button id="start" type="button">인식 시작</button><button id="stop" class="secondary" type="button" disabled>인식 중지</button><button id="clear" class="secondary" type="button">결과 지우기</button></div>
<div id="status" role="status" aria-live="polite">준비됨</div><section><h2>실시간 CLOVA 인식</h2><p id="partial">말씀해 보세요.</p></section><section><h2>확정 결과</h2><p id="final">아직 확정된 문장이 없습니다.</p></section></main>
<script>
const startButton=document.getElementById("start"),stopButton=document.getElementById("stop"),clearButton=document.getElementById("clear"),status=document.getElementById("status"),partial=document.getElementById("partial"),finalResult=document.getElementById("final");
let socket,context,stream,processor,source,completedText="",pending=[];
function setRunning(running){startButton.disabled=running;stopButton.disabled=!running}
function sendFrames(samples){pending.push(...samples);while(pending.length>=320){const frame=pending.splice(0,320);const pcm=new Int16Array(frame.length);for(let i=0;i<frame.length;i++)pcm[i]=Math.max(-32768,Math.min(32767,Math.round(frame[i]*32767)));socket.send(pcm.buffer)}}
async function start(){try{status.textContent="CLOVA 연결 중";socket=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/clova-test/ws`);socket.binaryType="arraybuffer";socket.onmessage=e=>{const message=JSON.parse(e.data);if(message.type==="ready"){status.textContent="듣는 중"}else if(message.type==="partial"){partial.textContent=message.text||"말씀해 보세요."}else if(message.type==="final"){completedText+=message.text;finalResult.textContent=completedText;partial.textContent="말씀해 보세요."}else if(message.type==="error"){status.textContent=`CLOVA 오류: ${message.message}`}};socket.onerror=()=>{status.textContent="CLOVA WebSocket 연결에 실패했습니다."};socket.onclose=()=>{setRunning(false);if(status.textContent==="듣는 중")status.textContent="인식이 중지되었습니다."};await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});stream=await navigator.mediaDevices.getUserMedia({audio:true});context=new AudioContext();source=context.createMediaStreamSource(stream);processor=context.createScriptProcessor(4096,1,1);processor.onaudioprocess=event=>{if(socket.readyState!==WebSocket.OPEN)return;const input=event.inputBuffer.getChannelData(0),ratio=context.sampleRate/16000,output=[];for(let index=0;index<input.length;index+=ratio)output.push(input[Math.floor(index)]);sendFrames(output)};source.connect(processor);processor.connect(context.destination);setRunning(true)}catch(error){status.textContent=`시작 실패: ${error.message||error}`;setRunning(false)}}
async function stop(){if(socket&&socket.readyState===WebSocket.OPEN){socket.send("flush");socket.close()}processor&&processor.disconnect();source&&source.disconnect();stream&&stream.getTracks().forEach(track=>track.stop());context&&await context.close();pending=[];setRunning(false)}
startButton.addEventListener("click",start);stopButton.addEventListener("click",stop);clearButton.addEventListener("click",()=>{completedText="";partial.textContent="말씀해 보세요.";finalResult.textContent="아직 확정된 문장이 없습니다."});
</script></body></html>"""


@app.get("/clova-test", response_class=HTMLResponse, include_in_schema=False)
async def clova_test_page() -> HTMLResponse:
    return HTMLResponse(PAGE)


def save_transcript(*, session_id: str, text: str, path: Path = TRANSCRIPT_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recordedAt": datetime.now(UTC).isoformat(),
        "sessionId": session_id,
        "text": text,
    }
    with path.open("a", encoding="utf-8") as transcript_log:
        transcript_log.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.websocket("/clova-test/ws")
async def clova_test_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = str(uuid4())
    settings = Settings()
    secret = settings.clova_secret_key
    if secret is None:
        await websocket.send_json({"type": "error", "message": "CLOVA Secret Key가 설정되지 않았습니다."})
        await websocket.close(code=1011)
        return

    speech = ClovaStreamingClient(
        secret_key=secret.get_secret_value(),
        target=settings.clova_grpc_target,
        language=settings.clova_language,
        boosting_keywords=(
            load_clova_keywords(settings.clova_keyword_file)
            if settings.clova_keyword_boosting_enabled
            else ()
        ),
        keyword_boosting_weight=settings.clova_keyword_weight,
        frame_bytes=settings.pcm_frame_bytes,
    )

    async def forward_events() -> None:
        async for event in speech.events():
            if event.kind is ClovaEventKind.ERROR:
                await websocket.send_json({"type": "error", "message": event.error or "알 수 없는 오류"})
                return
            if event.text:
                await websocket.send_json({"type": "partial", "text": event.text})

    try:
        await speech.start()
        listener = asyncio.create_task(forward_events())
        await websocket.send_json({"type": "ready"})
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes"):
                await speech.send_audio(message["bytes"])
            elif message.get("text") == "flush":
                final = await speech.flush(timeout_seconds=settings.clova_flush_timeout_seconds)
                text = final.text.strip()
                if text:
                    save_transcript(session_id=session_id, text=text)
                await websocket.send_json({"type": "final", "text": text})
                speech.reset_transcript()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        if "listener" in locals():
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
        await speech.close()
        with contextlib.suppress(Exception):
            await websocket.close()
