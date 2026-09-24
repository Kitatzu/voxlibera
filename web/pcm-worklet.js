// Vox Libera — AudioWorklet processor that downmixes to mono, resamples to
// 16 kHz, and converts to 16-bit PCM for the ingest WebSocket.
//
// Runs in the AudioWorkletGlobalScope: no access to window, no imports.
// The fractional resample position (sourcePosition) and the tail of
// unconsumed input samples (sourceBuffer) are kept on `this` across
// process() calls, so the linear interpolation is continuous across
// 128-sample render quanta and does not click at the boundaries.

const TARGET_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLES_PER_CHUNK = 1600; // 1600 samples * 2 bytes = 3200 bytes = 100ms at 16kHz.

class PCMDownsamplerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.sourceBuffer = [];
    this.sourcePosition = 0;
    this.outputInt16Buffer = new Int16Array(OUTPUT_SAMPLES_PER_CHUNK);
    this.outputWriteIndex = 0;
    this.sumOfSquaresForLevel = 0;
    this.sampleCountForLevel = 0;
  }

  process(inputList) {
    const inputChannels = inputList[0];
    if (!inputChannels || inputChannels.length === 0 || inputChannels[0].length === 0) {
      return true;
    }

    const frameCount = inputChannels[0].length;
    for (let frameIndex = 0; frameIndex < frameCount; frameIndex++) {
      let monoSample = 0;
      for (let channelIndex = 0; channelIndex < inputChannels.length; channelIndex++) {
        monoSample += inputChannels[channelIndex][frameIndex];
      }
      monoSample /= inputChannels.length;
      this.sourceBuffer.push(monoSample);
    }

    const resampleRatio = sampleRate / TARGET_SAMPLE_RATE;

    while (Math.floor(this.sourcePosition) + 1 < this.sourceBuffer.length) {
      const flooredIndex = Math.floor(this.sourcePosition);
      const fractionalPosition = this.sourcePosition - flooredIndex;
      const currentSample = this.sourceBuffer[flooredIndex];
      const nextSample = this.sourceBuffer[flooredIndex + 1];
      const interpolatedSample =
        currentSample + (nextSample - currentSample) * fractionalPosition;

      this.sumOfSquaresForLevel += interpolatedSample * interpolatedSample;
      this.sampleCountForLevel += 1;

      const clampedSample = Math.max(-1, Math.min(1, interpolatedSample));
      const int16Sample = Math.round(
        clampedSample < 0 ? clampedSample * 32768 : clampedSample * 32767
      );
      this.outputInt16Buffer[this.outputWriteIndex] = int16Sample;
      this.outputWriteIndex += 1;

      if (this.outputWriteIndex >= OUTPUT_SAMPLES_PER_CHUNK) {
        this.flushOutputChunk();
      }

      this.sourcePosition += resampleRatio;
    }

    // Drop fully-consumed source samples so sourceBuffer does not grow
    // without bound; keep the fractional remainder for continuity.
    const flooredPosition = Math.floor(this.sourcePosition);
    if (flooredPosition > 0) {
      this.sourceBuffer.splice(0, flooredPosition);
      this.sourcePosition -= flooredPosition;
    }

    return true;
  }

  flushOutputChunk() {
    const bufferToSend = this.outputInt16Buffer.buffer;
    this.port.postMessage({ type: "pcm", buffer: bufferToSend }, [bufferToSend]);

    const rootMeanSquare =
      this.sampleCountForLevel > 0
        ? Math.sqrt(this.sumOfSquaresForLevel / this.sampleCountForLevel)
        : 0;
    this.port.postMessage({ type: "level", rootMeanSquare });

    this.outputInt16Buffer = new Int16Array(OUTPUT_SAMPLES_PER_CHUNK);
    this.outputWriteIndex = 0;
    this.sumOfSquaresForLevel = 0;
    this.sampleCountForLevel = 0;
  }
}

registerProcessor("pcm-downsampler", PCMDownsamplerProcessor);
