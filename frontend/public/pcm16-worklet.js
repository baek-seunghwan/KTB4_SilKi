/* global AudioWorkletProcessor, registerProcessor, sampleRate */

class SilkiPcm16CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const processorOptions = options.processorOptions || {};
    this.targetSampleRate = processorOptions.targetSampleRate || 16000;
    this.frameSamples = processorOptions.frameSamples || 320;
    this.ratio = sampleRate / this.targetSampleRate;
    this.samples = new Float32Array(0);
    this.position = 0;
    this.frame = new Int16Array(this.frameSamples);
    this.frameOffset = 0;
    this.enabled = false;

    this.port.onmessage = (event) => {
      if (event.data?.type !== "set-enabled") {
        return;
      }

      this.enabled = Boolean(event.data.enabled);

      if (!this.enabled) {
        this.reset();
      }
    };
  }

  reset() {
    this.samples = new Float32Array(0);
    this.position = 0;
    this.frame = new Int16Array(this.frameSamples);
    this.frameOffset = 0;
  }

  append(input) {
    const combined = new Float32Array(this.samples.length + input.length);
    combined.set(this.samples);
    combined.set(input, this.samples.length);
    this.samples = combined;
  }

  encode(input) {
    this.append(input);

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

      if (this.frameOffset === this.frameSamples) {
        const frame = this.frame;
        this.port.postMessage(frame.buffer, [frame.buffer]);
        this.frame = new Int16Array(this.frameSamples);
        this.frameOffset = 0;
      }
    }

    const consumed = Math.floor(this.position);

    if (consumed > 0) {
      this.samples = this.samples.slice(consumed);
      this.position -= consumed;
    }
  }

  process(inputs, outputs) {
    const output = outputs[0]?.[0];
    output?.fill(0);

    if (!this.enabled) {
      return true;
    }

    const input = inputs[0]?.[0];

    if (input?.length) {
      this.encode(input);
    }

    return true;
  }
}

registerProcessor("silki-pcm16-capture", SilkiPcm16CaptureProcessor);
