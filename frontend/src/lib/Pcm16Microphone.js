const TARGET_SAMPLE_RATE = 16_000;
const FRAME_SAMPLES = 320;

class Pcm16FrameEncoder {
  constructor(sourceSampleRate, onFrame) {
    this.ratio = sourceSampleRate / TARGET_SAMPLE_RATE;
    this.onFrame = onFrame;
    this.samples = new Float32Array(0);
    this.position = 0;
    this.frame = new Int16Array(FRAME_SAMPLES);
    this.frameOffset = 0;
  }

  reset() {
    this.samples = new Float32Array(0);
    this.position = 0;
    this.frame = new Int16Array(FRAME_SAMPLES);
    this.frameOffset = 0;
  }

  push(input) {
    const combined = new Float32Array(this.samples.length + input.length);
    combined.set(this.samples);
    combined.set(input, this.samples.length);
    this.samples = combined;

    while (this.position + 1 < this.samples.length) {
      const index = Math.floor(this.position);
      const fraction = this.position - index;
      const sample =
        this.samples[index] * (1 - fraction) + this.samples[index + 1] * fraction;
      const clamped = Math.max(-1, Math.min(1, sample));

      this.frame[this.frameOffset] =
        clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      this.frameOffset += 1;
      this.position += this.ratio;

      if (this.frameOffset === FRAME_SAMPLES) {
        this.onFrame(this.frame.buffer);
        this.frame = new Int16Array(FRAME_SAMPLES);
        this.frameOffset = 0;
      }
    }

    const consumed = Math.floor(this.position);

    if (consumed > 0) {
      this.samples = this.samples.slice(consumed);
      this.position -= consumed;
    }
  }
}

export class Pcm16Microphone {
  constructor({ onFrame, onError }) {
    this.onFrame = onFrame;
    this.onError = onError;
    this.context = null;
    this.stream = null;
    this.source = null;
    this.captureNode = null;
    this.silentGain = null;
    this.encoder = null;
    this.enabled = false;
  }

  async start() {
    if (this.stream) {
      await this.resume();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("이 브라우저에서는 마이크를 사용할 수 없습니다.");
    }

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) {
      throw new Error("이 브라우저에서는 음성 처리를 사용할 수 없습니다.");
    }

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: { ideal: 1 },
        sampleRate: { ideal: TARGET_SAMPLE_RATE },
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });

    try {
      try {
        this.context = new AudioContextClass({
          latencyHint: "interactive",
          sampleRate: TARGET_SAMPLE_RATE,
        });
      } catch {
        // Safari versions that reject a requested sample rate still work with
        // the device rate; the encoder below resamples it to 16 kHz.
        this.context = new AudioContextClass({ latencyHint: "interactive" });
      }
      this.source = this.context.createMediaStreamSource(this.stream);
      this.silentGain = this.context.createGain();
      this.silentGain.gain.value = 0;

      if (this.context.audioWorklet && window.AudioWorkletNode) {
        const workletUrl = `${import.meta.env.BASE_URL}pcm16-worklet.js`;
        await this.context.audioWorklet.addModule(workletUrl);
        this.captureNode = new AudioWorkletNode(this.context, "silki-pcm16-capture", {
          channelCount: 1,
          channelCountMode: "explicit",
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [1],
          processorOptions: {
            targetSampleRate: TARGET_SAMPLE_RATE,
            frameSamples: FRAME_SAMPLES,
          },
        });
        this.captureNode.port.onmessage = (event) => {
          if (this.enabled && event.data instanceof ArrayBuffer) {
            this.onFrame(event.data);
          }
        };
        this.captureNode.onprocessorerror = () => {
          this.onError?.(new Error("마이크 음성 처리기가 중단되었습니다."));
        };
      } else {
        this.encoder = new Pcm16FrameEncoder(this.context.sampleRate, (frame) => {
          if (this.enabled) {
            this.onFrame(frame);
          }
        });
        this.captureNode = this.context.createScriptProcessor(2048, 1, 1);
        this.captureNode.onaudioprocess = (event) => {
          if (!this.enabled) {
            return;
          }

          this.encoder.push(event.inputBuffer.getChannelData(0));
          event.outputBuffer.getChannelData(0).fill(0);
        };
      }

      this.source.connect(this.captureNode);
      this.captureNode.connect(this.silentGain);
      this.silentGain.connect(this.context.destination);
      await this.resume();
    } catch (error) {
      await this.stop();
      throw error;
    }
  }

  async resume() {
    if (!this.context) {
      return;
    }

    if (this.context.state === "suspended") {
      await this.context.resume();
    }

    this.enabled = true;
    this.captureNode?.port?.postMessage({ type: "set-enabled", enabled: true });
  }

  pause() {
    this.enabled = false;
    this.encoder?.reset();
    this.captureNode?.port?.postMessage({ type: "set-enabled", enabled: false });
  }

  async stop() {
    this.enabled = false;
    this.captureNode?.port?.postMessage({ type: "set-enabled", enabled: false });

    if (this.captureNode) {
      this.captureNode.disconnect();
      this.captureNode.onaudioprocess = null;
      this.captureNode = null;
    }

    this.source?.disconnect();
    this.source = null;
    this.silentGain?.disconnect();
    this.silentGain = null;
    this.encoder = null;

    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;

    if (this.context && this.context.state !== "closed") {
      await this.context.close();
    }

    this.context = null;
  }
}
