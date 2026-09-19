/* global AudioWorkletProcessor, sampleRate, registerProcessor */
/* AudioWorklet runs off the UI thread. Box-filter resampling keeps frame timing
 * independent of the hardware rate; frames are 100 ms of mono PCM16LE. */
class ChangweiPcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.ratio = sampleRate / 16000
    this.weight = 0
    this.sum = 0
    this.frame = new Int16Array(1600)
    this.length = 0
    this.stopped = false
    this.port.onmessage = ({ data }) => {
      if (data.type !== 'flush') return
      this.stopped = true
      if (this.weight > 0) this.append(this.sum / this.weight)
      this.emit()
      this.port.postMessage({ type: 'flushed' })
    }
  }

  append(sample) {
    const clipped = Math.max(-1, Math.min(1, sample))
    this.frame[this.length++] = Math.round(clipped * (clipped < 0 ? 32768 : 32767))
    if (this.length === this.frame.length) this.emit()
  }

  emit() {
    if (!this.length) return
    const buffer = new ArrayBuffer(this.length * 2)
    const view = new DataView(buffer)
    for (let i = 0; i < this.length; i++) view.setInt16(i * 2, this.frame[i], true)
    this.port.postMessage({ type: 'audio', buffer }, [buffer])
    this.length = 0
  }

  process(inputs) {
    if (this.stopped) return false
    const channels = inputs[0]
    if (!channels?.length) return true
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0
      for (const channel of channels) sample += channel[i] / channels.length
      let remaining = 1
      while (remaining > 1e-8) {
        const weight = Math.min(remaining, this.ratio - this.weight)
        this.sum += sample * weight
        this.weight += weight
        remaining -= weight
        if (this.weight >= this.ratio - 1e-8) {
          this.append(this.sum / this.ratio)
          this.weight = 0
          this.sum = 0
        }
      }
    }
    return true
  }
}
registerProcessor('changwei-pcm', ChangweiPcmProcessor)
