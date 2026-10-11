# CLOVA Speech 프로토콜

저장소의 `proto/nest.proto`는
[Naver Cloud CLOVA Speech 스트리밍 가이드](https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech-grpc)의
공식 계약입니다. 새 클론과 Docker 빌드가 동일한 입력을 사용하도록 proto 원본은 추적하고,
생성된 Python 스텁만 추적하지 않습니다.

로컬 Python 스텁 생성:

```bash
python scripts/generate_clova_proto.py
```

공식 계약이 변경되면 위 문서와 대조해 `nest.proto`를 갱신한 뒤 스텁 생성, 단위 테스트,
CLOVA 실제 스트림 스모크 테스트를 함께 실행해야 합니다. Docker 빌드는 이미지 안에서
같은 생성 스크립트를 실행합니다.
