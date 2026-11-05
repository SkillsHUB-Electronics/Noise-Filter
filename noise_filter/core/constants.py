SAMPLE_RATE = 48_000
FRAME_SIZE = 480  # 10 ms @ 48 kHz; same frame size RNNoise / DeepFilterNet use
FRAME_MS = 1000.0 * FRAME_SIZE / SAMPLE_RATE
