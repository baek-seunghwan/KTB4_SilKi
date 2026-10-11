# Fish Audio S2 Pro AWS 배포

Fish Audio는 Silki FastAPI와 같은 프로세스나 같은 EC2에 넣지 않습니다. GPU 전용 private
subnet EC2에서 공식 Fish Speech API 서버를 실행하고, FastAPI만 private HTTP로 접근합니다.

## 권장 토폴로지

```text
Internet
   X (직접 접근 없음)

AI EC2 / ECS (sg-silki-ai)
   └─ TCP 8080, private IP/DNS
          ↓
GPU EC2 (sg-fish-audio, private subnet)
   └─ Docker + NVIDIA runtime + S2 Pro /v1/tts
```

- NVIDIA VRAM 24GB 이상을 사용합니다. 예: A10G 24GB가 있는 `g5.xlarge` 이상.
- GPU EC2 inbound TCP 8080의 source는 `sg-silki-ai` 하나만 허용합니다.
- 8080을 `0.0.0.0/0`, public ALB, CloudFront 또는 public IP에 노출하지 않습니다.
- 운영 접속은 SSH 공개 대신 SSM Session Manager를 권장합니다.
- AI SG outbound TCP 8080은 `sg-fish-audio`로만 제한합니다.

## GPU 호스트 준비 및 실행

AWS Deep Learning AMI 또는 호환 NVIDIA 드라이버를 사용하고 Docker Engine, Docker Compose,
NVIDIA Container Toolkit을 설치한 뒤 `nvidia-smi`와 다음 명령으로 GPU 전달을 확인합니다.

```bash
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

Fish Speech 저장소는 검증한 release/commit으로 고정하고 공식 CUDA server target을 빌드합니다.
S2 Pro 체크포인트는 `/app/checkpoints/s2-pro`에 마운트되어야 합니다.

```bash
git clone https://github.com/fishaudio/fish-speech.git
cd fish-speech
git checkout <검증한-release-or-commit>
docker build --platform linux/amd64 \
  -f docker/Dockerfile \
  --build-arg BACKEND=cuda \
  --build-arg CUDA_VER=12.6.0 \
  --build-arg UV_EXTRA=cu126 \
  --target server \
  -t fish-speech-server:s2-pro .
```

API 서버는 반드시 S2 Pro 체크포인트와 API Key로 시작합니다. 아래의
`/run/secrets/fish_api_key`는 부팅 시 AWS Secrets Manager/SSM에서 가져와 mode `0400`으로
만든 런타임 파일이며 이미지, Git, user-data 평문에 포함하면 안 됩니다. 공식 컨테이너의
UID/GID `1000:1000`이 읽을 수 있도록 소유권도 맞춥니다.

```bash
docker run -d --name fish-speech-s2-pro --restart unless-stopped \
  --gpus all --shm-size 16g \
  -p 8080:8080 \
  --health-cmd='curl -fsS -H "Authorization: Bearer $(cat /run/secrets/fish_api_key)" http://127.0.0.1:8080/v1/health || exit 1' \
  --health-interval=30s --health-timeout=10s \
  --health-start-period=120s --health-retries=3 \
  -v /opt/fish-speech/checkpoints:/app/checkpoints:ro \
  -v /opt/fish-speech/references:/app/references:ro \
  -v /run/secrets/fish_api_key:/run/secrets/fish_api_key:ro \
  --entrypoint /bin/bash \
  fish-speech-server:s2-pro \
  -lc 'exec uv run --no-sync python tools/api_server.py --listen 0.0.0.0:8080 --half --compile --llama-checkpoint-path checkpoints/s2-pro --decoder-checkpoint-path checkpoints/s2-pro/codec.pth --decoder-config-name modded_dac_vq --api-key "$(cat /run/secrets/fish_api_key)"'
```

보안 그룹이 적용된 AI 호스트에서만 상태와 인증을 확인합니다.

```bash
curl --fail http://<fish-private-ip>:8080/v1/health \
  -H "Authorization: Bearer ${FISH_API_KEY}"
curl --fail -X POST 'http://<fish-private-ip>:8080/v1/tts' \
  -H "Authorization: Bearer ${FISH_API_KEY}" \
  -H 'Content-Type: application/json' \
  --data '{"text":"연결 테스트입니다.","references":[],"reference_id":null,"format":"mp3","streaming":false}' \
  --output smoke.mp3
```

## FastAPI 설정

AI 런타임에는 다음 값만 주입합니다. URL에는 `/v1/tts`를 붙이지 않습니다.

```dotenv
SILKI_AI_FISH_TTS_ENABLED=true
SILKI_AI_FISH_TTS_BASE_URL=http://<fish-private-ip-or-private-dns>:8080
SILKI_AI_FISH_TTS_API_KEY=<같은 Secrets Manager 값>
SILKI_AI_FISH_TTS_REFERENCE_ID=
SILKI_AI_FISH_TTS_FORMAT=mp3
SILKI_AI_FISH_TTS_TIMEOUT_SECONDS=20
SILKI_AI_FISH_TTS_MAX_AUDIO_BYTES=5242880
```

`referenceId`는 선택 화자이며 S2 Pro 모델 선택값이 아닙니다. S2 Pro는 Fish 서버 시작 시
체크포인트로 고정됩니다. GPU 서버가 느리거나 중단되면 AI는 후보를 이미 전달한 상태에서 TTS만
건너뜁니다.

공식 실행 계약은 Fish Speech의
[server 문서](https://github.com/fishaudio/fish-speech/blob/main/docs/en/server.md)와
[Docker 설치 문서](https://github.com/fishaudio/fish-speech/blob/main/docs/en/install.md)를 기준으로 했습니다.
