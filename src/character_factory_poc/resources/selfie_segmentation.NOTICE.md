# selfie_segmentation.tflite

MediaPipe Selfie Segmentation (general, 256×256) 모델 파일이다. mediapipe 0.10.21 휠의
`mediapipe/modules/selfie_segmentation/selfie_segmentation.tflite`를 그대로 복사했다
(sha256 9ee168ec7c8f2a16c56fe8e1cfbc514974cbbb7e434051b455635f1bd1462f5c).

- 출처: https://github.com/google-ai-edge/mediapipe
- 라이선스: Apache License 2.0 (Copyright Google LLC)
- 쓰는 곳: `stages/s6_actions/bg_lock.py` — 시그니처 영상의 배경을 기준 사진 배경으로 고정한다(D-0222).
