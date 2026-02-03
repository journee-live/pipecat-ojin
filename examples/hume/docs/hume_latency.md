2026-02-03 16:44:44.478 | DEBUG    | pipecat.pipeline.task:_wait_for_pipeline_end:715 - PipelineTask#0: EndFrame#0(reason: None) reached the end of the pipeline, pipeline is closing.
2026-02-03 16:44:44.478 | DEBUG    | pipecat.pipeline.task:run:580 - Pipeline task PipelineTask#0 is finishing...
2026-02-03 16:44:44.478 | DEBUG    | pipecat.pipeline.task:run:585 - Pipeline task PipelineTask#0 has finished
2026-02-03 16:44:44.478 | DEBUG    | pipecat.pipeline.runner:run:95 - Runner PipelineRunner#0 finished running PipelineTask#0
2026-02-03 16:44:44.478 | INFO     | __main__:print_summary:80 - 
============================================================
2026-02-03 16:44:44.478 | INFO     | __main__:print_summary:81 - LATENCY TEST SUMMARY (OLD HUME SERVICE)
2026-02-03 16:44:44.478 | INFO     | __main__:print_summary:82 - ============================================================
2026-02-03 16:44:44.479 | SUCCESS  | __main__:print_summary:86 - ⏱️  Time to first audio: 7971ms
2026-02-03 16:44:44.479 | INFO     | __main__:print_summary:90 - ⏱️  Time to first transcript: 7514ms
2026-02-03 16:44:44.479 | INFO     | __main__:print_summary:92 - 📊 Audio chunks received: 4
2026-02-03 16:44:44.479 | INFO     | __main__:print_summary:93 - 🎵 Total audio duration: 3.74s
2026-02-03 16:44:44.479 | INFO     | __main__:print_summary:96 - 👤 User said: 'Can you tell me a short sentence?'
2026-02-03 16:44:44.479 | INFO     | __main__:print_summary:98 - 🤖 Assistant said: 'I'm Michael. What's your name, young gun?'
2026-02-03 16:44:44.479 | INFO     | __main__:print_summary:100 - ============================================================
(venv) ➜  hume git:(main) ✗ 
(venv) ➜  hume git:(main) ✗  cd /home/ubuntu/pipecat-ojin/examples/hume ; /usr/bin/env /home/ubuntu/pipecat-ojin/examples/hume/venv/bin/python /root/.windsurf
-server/extensions/ms-python.debugpy-2025.14.1-linux-x64/bundled/libs/debugpy/adapter/../../debugpy/launcher 60277 -- test_latency_hume.py 
2026-02-03 16:47:33.549 | INFO     | pipecat:<module>:14 - ᓚᘏᗢ Pipecat 0.0.77.dev329 (Python 3.12.3 (main, Jan  8 2026, 11:30:50) [GCC 13.3.0]) ᓚᘏᗢ
2026-02-03 16:47:36.198 | INFO     | __main__:main:186 - 🎯 Starting Hume Latency Test (OLD SERVICE - hume 0.12.1)
2026-02-03 16:47:36.198 | INFO     | __main__:main:187 - ============================================================
2026-02-03 16:47:36.198 | DEBUG    | pipecat.services.hume.hume:__init__:89 - Initializing HumeSTSService
/home/ubuntu/pipecat-ojin/src/pipecat/services/hume/hume.py:107: DeprecationWarning: `create_default_resampler` is deprecated. Use `create_stream_resampler` for real-time processing scenarios or `create_file_resampler` for batch processing of complete audio files.
  self._resampler = create_default_resampler()
2026-02-03 16:47:36.214 | DEBUG    | pipecat.processors.frame_processor:link:564 - Linking Pipeline#0::Source -> HumeSTSService#0
2026-02-03 16:47:36.214 | DEBUG    | pipecat.processors.frame_processor:link:564 - Linking HumeSTSService#0 -> LatencyMeasurementProcessor#0
2026-02-03 16:47:36.214 | DEBUG    | pipecat.processors.frame_processor:link:564 - Linking LatencyMeasurementProcessor#0 -> Pipeline#0::Sink
2026-02-03 16:47:36.214 | DEBUG    | pipecat.processors.frame_processor:link:564 - Linking PipelineTask#0::Source -> RTVIProcessor#0
2026-02-03 16:47:36.214 | DEBUG    | pipecat.processors.frame_processor:link:564 - Linking RTVIProcessor#0 -> Pipeline#0
2026-02-03 16:47:36.214 | DEBUG    | pipecat.processors.frame_processor:link:564 - Linking Pipeline#0 -> PipelineTask#0::Sink
2026-02-03 16:47:36.214 | DEBUG    | pipecat.pipeline.runner:run:71 - Runner PipelineRunner#0 started running PipelineTask#0
2026-02-03 16:47:36.214 | INFO     | __main__:send_wav_file:107 - 📂 Reading WAV file: short.wav
2026-02-03 16:47:36.215 | INFO     | __main__:send_wav_file:114 - 🎵 WAV info: 48000Hz, 1 channel(s), 122400 frames
2026-02-03 16:47:36.215 | INFO     | __main__:send_wav_file:121 - ⏱️  Audio duration: 2.55s
2026-02-03 16:47:36.215 | DEBUG    | pipecat.pipeline.task:_wait_for_pipeline_start:687 - PipelineTask#0: Starting. Waiting for StartFrame#0 to reach the end of the pipeline...
2026-02-03 16:47:36.216 | DEBUG    | pipecat.pipeline.task:_wait_for_pipeline_start:690 - PipelineTask#0: StartFrame#0 reached the end of the pipeline, pipeline is now ready.
2026-02-03 16:47:36.555 | INFO     | pipecat.services.hume.hume:_on_open:214 - Connected to Hume EVI
2026-02-03 16:47:38.186 | INFO     | pipecat.services.hume.hume:_on_message:275 - Hume chat metadata: chat_group_id='06b6a419-bcc1-42b1-857e-ce1c0fb67e8c' chat_id='abd8bd48-771f-432a-b371-631f16769918' custom_session_id=None request_id='e4cf5693-b307-4970-a205-7fd09ea24b4c343831' type='chat_metadata'
2026-02-03 16:47:42.220 | INFO     | __main__:send_wav_file:126 - 🚀 Sending audio to Hume...
2026-02-03 16:47:42.220 | INFO     | __main__:send_wav_file:131 - 🎵 Sending WAV audio...
2026-02-03 16:47:42.220 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.4
2026-02-03 16:47:42.220 | INFO     | pipecat.services.hume.hume:process_frame:149 - 📝 Recording sent audio to: sent_audio_debug.wav
2026-02-03 16:47:42.241 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.8
2026-02-03 16:47:42.263 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.3
2026-02-03 16:47:42.286 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.9
2026-02-03 16:47:42.309 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.7
2026-02-03 16:47:42.331 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.2
2026-02-03 16:47:42.354 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 2.7
2026-02-03 16:47:42.377 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.6
2026-02-03 16:47:42.400 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.3
2026-02-03 16:47:42.422 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.7
2026-02-03 16:47:42.445 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.8
2026-02-03 16:47:42.468 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.5
2026-02-03 16:47:42.490 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.5
2026-02-03 16:47:42.513 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 2.2
2026-02-03 16:47:42.536 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.9
2026-02-03 16:47:42.558 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.1
2026-02-03 16:47:42.581 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.581674
2026-02-03 16:47:42.581 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.604 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.604394
2026-02-03 16:47:42.604 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.627 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.6272192
2026-02-03 16:47:42.627 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.650 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.649994
2026-02-03 16:47:42.650 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.672 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.6728952
2026-02-03 16:47:42.673 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.695 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.695601
2026-02-03 16:47:42.695 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.718 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.7184403
2026-02-03 16:47:42.718 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.741 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.7411551
2026-02-03 16:47:42.741 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.763 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.7638533
2026-02-03 16:47:42.763 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.786 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.7868168
2026-02-03 16:47:42.786 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.809 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.8095734
2026-02-03 16:47:42.809 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.832 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.8324273
2026-02-03 16:47:42.832 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.855 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.8551717
2026-02-03 16:47:42.855 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.877 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.8779051
2026-02-03 16:47:42.878 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.900 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.9007246
2026-02-03 16:47:42.900 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.923 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.9233932
2026-02-03 16:47:42.923 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.946 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.9460995
2026-02-03 16:47:42.946 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.968 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.968774
2026-02-03 16:47:42.968 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:42.991 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133662.9915848
2026-02-03 16:47:42.991 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.014 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.014272
2026-02-03 16:47:43.014 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.036 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.036966
2026-02-03 16:47:43.037 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.059 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.0596616
2026-02-03 16:47:43.059 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.082 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.0824034
2026-02-03 16:47:43.082 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.105 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.10509
2026-02-03 16:47:43.105 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.127 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.127821
2026-02-03 16:47:43.127 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.150 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.1505318
2026-02-03 16:47:43.150 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.173 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.1732075
2026-02-03 16:47:43.173 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.195 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.1959252
2026-02-03 16:47:43.196 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.217 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.2171621
2026-02-03 16:47:43.217 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.239 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.2399762
2026-02-03 16:47:43.240 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.262 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.262683
2026-02-03 16:47:43.262 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.285 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.2854097
2026-02-03 16:47:43.285 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.308 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.3081565
2026-02-03 16:47:43.308 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.330 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.3309534
2026-02-03 16:47:43.331 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.353 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.353666
2026-02-03 16:47:43.353 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.376 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.3763456
2026-02-03 16:47:43.376 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.399 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.399028
2026-02-03 16:47:43.399 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.421 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.3
2026-02-03 16:47:43.444 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 6.3
2026-02-03 16:47:43.466 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 3.2
2026-02-03 16:47:43.489 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 2.5
2026-02-03 16:47:43.511 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.5118687
2026-02-03 16:47:43.512 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.534 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.534768
2026-02-03 16:47:43.534 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.556 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.5567427
2026-02-03 16:47:43.556 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.578 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.578015
2026-02-03 16:47:43.578 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.600 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.600729
2026-02-03 16:47:43.600 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.623 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.6234555
2026-02-03 16:47:43.623 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.646 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.646196
2026-02-03 16:47:43.646 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.668 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133663.6688774
2026-02-03 16:47:43.668 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:43.691 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.1
2026-02-03 16:47:43.712 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 145.4
2026-02-03 16:47:43.735 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 321.2
2026-02-03 16:47:43.758 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 252.2
2026-02-03 16:47:43.780 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 125.5
2026-02-03 16:47:43.803 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 89.6
2026-02-03 16:47:43.826 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 212.2
2026-02-03 16:47:43.849 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 453.9
2026-02-03 16:47:43.871 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 580.6
2026-02-03 16:47:43.894 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 702.2
2026-02-03 16:47:43.917 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 921.7
2026-02-03 16:47:43.940 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 707.3
2026-02-03 16:47:43.962 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 720.8
2026-02-03 16:47:43.985 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 625.2
2026-02-03 16:47:44.008 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 533.9
2026-02-03 16:47:44.031 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 440.4
2026-02-03 16:47:44.053 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 637.8
2026-02-03 16:47:44.076 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 689.8
2026-02-03 16:47:44.099 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 574.1
2026-02-03 16:47:44.120 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 569.7
2026-02-03 16:47:44.141 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 570.5
2026-02-03 16:47:44.163 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 628.1
2026-02-03 16:47:44.184 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 637.6
2026-02-03 16:47:44.207 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 653.4
2026-02-03 16:47:44.230 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 671.9
2026-02-03 16:47:44.253 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 631.1
2026-02-03 16:47:44.275 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 554.0
2026-02-03 16:47:44.298 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 560.6
2026-02-03 16:47:44.319 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 549.2
2026-02-03 16:47:44.342 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 521.0
2026-02-03 16:47:44.364 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 567.6
2026-02-03 16:47:44.387 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 512.3
2026-02-03 16:47:44.410 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 341.1
2026-02-03 16:47:44.433 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 140.3
2026-02-03 16:47:44.455 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 60.1
2026-02-03 16:47:44.478 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 48.5
2026-02-03 16:47:44.501 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 29.2
2026-02-03 16:47:44.524 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 28.9
2026-02-03 16:47:44.546 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 42.1
2026-02-03 16:47:44.569 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 43.9
2026-02-03 16:47:44.592 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 19.3
2026-02-03 16:47:44.615 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 42.7
2026-02-03 16:47:44.637 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 14.8
2026-02-03 16:47:44.660 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 12.9
2026-02-03 16:47:44.683 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 22.3
2026-02-03 16:47:44.706 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 147.1
2026-02-03 16:47:44.728 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 203.4
2026-02-03 16:47:44.751 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 205.3
2026-02-03 16:47:44.774 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 658.3
2026-02-03 16:47:44.797 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 743.5
2026-02-03 16:47:44.819 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1072.0
2026-02-03 16:47:44.842 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1081.3
2026-02-03 16:47:44.865 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 941.5
2026-02-03 16:47:44.888 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 826.6
2026-02-03 16:47:44.911 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 743.6
2026-02-03 16:47:44.933 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 725.7
2026-02-03 16:47:44.956 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 449.4
2026-02-03 16:47:44.979 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 228.5
2026-02-03 16:47:45.002 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 336.0
2026-02-03 16:47:45.024 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 396.4
2026-02-03 16:47:45.047 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 397.4
2026-02-03 16:47:45.070 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 395.1
2026-02-03 16:47:45.093 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 407.8
2026-02-03 16:47:45.115 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 426.3
2026-02-03 16:47:45.138 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 442.8
2026-02-03 16:47:45.161 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 452.1
2026-02-03 16:47:45.184 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 476.9
2026-02-03 16:47:45.206 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 489.7
2026-02-03 16:47:45.229 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 496.0
2026-02-03 16:47:45.252 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 492.0
2026-02-03 16:47:45.275 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 559.0
2026-02-03 16:47:45.297 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 599.5
2026-02-03 16:47:45.320 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 598.1
2026-02-03 16:47:45.343 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 614.5
2026-02-03 16:47:45.365 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 608.3
2026-02-03 16:47:45.386 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 569.3
2026-02-03 16:47:45.408 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 531.6
2026-02-03 16:47:45.431 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 661.4
2026-02-03 16:47:45.454 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 667.2
2026-02-03 16:47:45.477 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 665.3
2026-02-03 16:47:45.499 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 645.4
2026-02-03 16:47:45.522 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 584.8
2026-02-03 16:47:45.545 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 487.6
2026-02-03 16:47:45.568 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 677.0
2026-02-03 16:47:45.590 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 599.9
2026-02-03 16:47:45.612 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 541.1
2026-02-03 16:47:45.635 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 442.5
2026-02-03 16:47:45.658 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 720.8
2026-02-03 16:47:45.681 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 598.8
2026-02-03 16:47:45.704 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 364.0
2026-02-03 16:47:45.726 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 419.8
2026-02-03 16:47:45.749 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 286.5
2026-02-03 16:47:45.772 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 241.9
2026-02-03 16:47:45.794 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 161.9
2026-02-03 16:47:45.817 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 115.1
2026-02-03 16:47:45.839 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 123.5
2026-02-03 16:47:45.862 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 184.8
2026-02-03 16:47:45.884 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 230.1
2026-02-03 16:47:45.907 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 292.5
2026-02-03 16:47:45.930 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 423.0
2026-02-03 16:47:45.953 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 511.7
2026-02-03 16:47:45.976 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 464.9
2026-02-03 16:47:45.999 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 636.7
2026-02-03 16:47:46.021 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 552.0
2026-02-03 16:47:46.044 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1345.4
2026-02-03 16:47:46.067 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 624.7
2026-02-03 16:47:46.090 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 466.9
2026-02-03 16:47:46.112 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 470.4
2026-02-03 16:47:46.135 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 271.9
2026-02-03 16:47:46.158 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 137.0
2026-02-03 16:47:46.181 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 94.3
2026-02-03 16:47:46.204 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 56.8
2026-02-03 16:47:46.227 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 60.9
2026-02-03 16:47:46.249 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 51.1
2026-02-03 16:47:46.272 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 191.8
2026-02-03 16:47:46.295 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 386.1
2026-02-03 16:47:46.318 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 381.2
2026-02-03 16:47:46.340 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 279.3
2026-02-03 16:47:46.363 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 420.5
2026-02-03 16:47:46.386 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 466.4
2026-02-03 16:47:46.407 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 386.3
2026-02-03 16:47:46.429 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 320.9
2026-02-03 16:47:46.452 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 513.2
2026-02-03 16:47:46.474 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 448.5
2026-02-03 16:47:46.497 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 325.1
2026-02-03 16:47:46.520 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 385.1
2026-02-03 16:47:46.541 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 482.2
2026-02-03 16:47:46.564 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 392.8
2026-02-03 16:47:46.587 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 319.0
2026-02-03 16:47:46.610 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 382.7
2026-02-03 16:47:46.632 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 383.2
2026-02-03 16:47:46.655 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 316.5
2026-02-03 16:47:46.678 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 208.4
2026-02-03 16:47:46.701 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 127.7
2026-02-03 16:47:46.723 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 202.5
2026-02-03 16:47:46.746 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 207.7
2026-02-03 16:47:46.769 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 157.6
2026-02-03 16:47:46.792 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 109.0
2026-02-03 16:47:46.815 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 128.1
2026-02-03 16:47:46.837 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 292.4
2026-02-03 16:47:46.860 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 282.3
2026-02-03 16:47:46.883 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 330.5
2026-02-03 16:47:46.906 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 440.8
2026-02-03 16:47:46.929 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 571.5
2026-02-03 16:47:46.951 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 753.7
2026-02-03 16:47:46.974 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 530.7
2026-02-03 16:47:46.997 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1163.9
2026-02-03 16:47:47.019 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1066.2
2026-02-03 16:47:47.042 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 594.2
2026-02-03 16:47:47.065 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 654.4
2026-02-03 16:47:47.087 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 517.9
2026-02-03 16:47:47.110 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 330.9
2026-02-03 16:47:47.133 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 200.2
2026-02-03 16:47:47.156 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 117.4
2026-02-03 16:47:47.178 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 86.9
2026-02-03 16:47:47.201 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 110.4
2026-02-03 16:47:47.224 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 223.2
2026-02-03 16:47:47.247 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 467.6
2026-02-03 16:47:47.270 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 383.5
2026-02-03 16:47:47.292 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 328.6
2026-02-03 16:47:47.315 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 436.6
2026-02-03 16:47:47.338 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 460.3
2026-02-03 16:47:47.360 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 406.3
2026-02-03 16:47:47.383 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 366.7
2026-02-03 16:47:47.404 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 247.6
2026-02-03 16:47:47.427 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 399.9
2026-02-03 16:47:47.450 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 482.7
2026-02-03 16:47:47.473 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 392.2
2026-02-03 16:47:47.495 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 327.3
2026-02-03 16:47:47.518 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 435.1
2026-02-03 16:47:47.541 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 412.4
2026-02-03 16:47:47.564 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 304.3
2026-02-03 16:47:47.586 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 119.8
2026-02-03 16:47:47.609 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 61.0
2026-02-03 16:47:47.632 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 88.8
2026-02-03 16:47:47.655 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 30.6
2026-02-03 16:47:47.677 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 13.3
2026-02-03 16:47:47.700 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 15.6
2026-02-03 16:47:47.723 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 14.8
2026-02-03 16:47:47.746 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 20.4
2026-02-03 16:47:47.768 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 196.7
2026-02-03 16:47:47.790 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 139.6
2026-02-03 16:47:47.813 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 106.0
2026-02-03 16:47:47.835 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 144.5
2026-02-03 16:47:47.858 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 481.9
2026-02-03 16:47:47.881 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 405.3
2026-02-03 16:47:47.904 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 402.8
2026-02-03 16:47:47.926 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 401.2
2026-02-03 16:47:47.949 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 378.1
2026-02-03 16:47:47.972 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 339.0
2026-02-03 16:47:47.994 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 255.2
2026-02-03 16:47:48.017 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 227.0
2026-02-03 16:47:48.040 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 204.6
2026-02-03 16:47:48.063 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 278.2
2026-02-03 16:47:48.084 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 282.8
2026-02-03 16:47:48.105 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 296.0
2026-02-03 16:47:48.128 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 317.5
2026-02-03 16:47:48.150 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 334.4
2026-02-03 16:47:48.173 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 339.8
2026-02-03 16:47:48.195 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 287.8
2026-02-03 16:47:48.218 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 228.9
2026-02-03 16:47:48.241 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 135.1
2026-02-03 16:47:48.264 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 50.4
2026-02-03 16:47:48.286 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 21.5
2026-02-03 16:47:48.309 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 24.1
2026-02-03 16:47:48.332 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 68.8
2026-02-03 16:47:48.354 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 115.8
2026-02-03 16:47:48.377 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 124.1
2026-02-03 16:47:48.400 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 132.4
2026-02-03 16:47:48.423 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 243.5
2026-02-03 16:47:48.445 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 190.5
2026-02-03 16:47:48.468 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 256.5
2026-02-03 16:47:48.491 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 196.7
2026-02-03 16:47:48.514 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 233.6
2026-02-03 16:47:48.536 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 253.1
2026-02-03 16:47:48.557 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 165.0
2026-02-03 16:47:48.580 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 71.9
2026-02-03 16:47:48.603 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 58.3
2026-02-03 16:47:48.625 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 51.2
2026-02-03 16:47:48.648 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 34.2
2026-02-03 16:47:48.671 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 58.0
2026-02-03 16:47:48.694 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 45.3
2026-02-03 16:47:48.715 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 12.1
2026-02-03 16:47:48.738 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 11.1
2026-02-03 16:47:48.761 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 9.0
2026-02-03 16:47:48.784 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 10.2
2026-02-03 16:47:48.805 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 14.1
2026-02-03 16:47:48.828 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 16.9
2026-02-03 16:47:48.850 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 10.5
2026-02-03 16:47:48.873 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 8.0
2026-02-03 16:47:48.896 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 17.2
2026-02-03 16:47:48.919 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 13.9
2026-02-03 16:47:48.941 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 8.4
2026-02-03 16:47:48.964 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 1.9
2026-02-03 16:47:48.987 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133668.987226
2026-02-03 16:47:48.987 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.010 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.009989
2026-02-03 16:47:49.010 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.032 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.0327308
2026-02-03 16:47:49.032 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.055 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.0555804
2026-02-03 16:47:49.055 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.077 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.0776362
2026-02-03 16:47:49.077 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.100 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.100351
2026-02-03 16:47:49.100 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.123 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.1231024
2026-02-03 16:47:49.123 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.145 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.1458485
2026-02-03 16:47:49.145 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.168 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.168571
2026-02-03 16:47:49.168 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.191 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.191347
2026-02-03 16:47:49.191 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.214 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.2141087
2026-02-03 16:47:49.214 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.236 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.2367918
2026-02-03 16:47:49.236 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.259 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.2594726
2026-02-03 16:47:49.259 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.281 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.2813816
2026-02-03 16:47:49.281 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.304 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.3040485
2026-02-03 16:47:49.304 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.326 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.3267484
2026-02-03 16:47:49.326 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.349 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.3496206
2026-02-03 16:47:49.349 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.371 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.371885
2026-02-03 16:47:49.372 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.394 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.3946276
2026-02-03 16:47:49.394 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.417 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.4173284
2026-02-03 16:47:49.417 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.440 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.4400232
2026-02-03 16:47:49.440 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.462 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.4626935
2026-02-03 16:47:49.462 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.485 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.485535
2026-02-03 16:47:49.485 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.508 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.5082324
2026-02-03 16:47:49.508 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.530 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.5308914
2026-02-03 16:47:49.531 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.553 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.55359
2026-02-03 16:47:49.553 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.576 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.5763257
2026-02-03 16:47:49.576 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.599 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.599062
2026-02-03 16:47:49.599 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.621 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.6218793
2026-02-03 16:47:49.622 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.644 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.6445935
2026-02-03 16:47:49.644 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.667 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.6672807
2026-02-03 16:47:49.667 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.689 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.689976
2026-02-03 16:47:49.690 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.712 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.7126675
2026-02-03 16:47:49.712 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.735 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.7353616
2026-02-03 16:47:49.735 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.758 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.7580855
2026-02-03 16:47:49.758 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.780 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.7807703
2026-02-03 16:47:49.780 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.803 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.8034954
2026-02-03 16:47:49.803 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.824 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.8244839
2026-02-03 16:47:49.824 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.845 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.845582
2026-02-03 16:47:49.845 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.867 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.8678613
2026-02-03 16:47:49.868 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.890 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.8907607
2026-02-03 16:47:49.890 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.913 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.91347
2026-02-03 16:47:49.913 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.936 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.9361427
2026-02-03 16:47:49.936 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.958 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.9588315
2026-02-03 16:47:49.958 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:49.981 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133669.9815123
2026-02-03 16:47:49.981 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.004 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.0041726
2026-02-03 16:47:50.004 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.026 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.0268414
2026-02-03 16:47:50.026 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.049 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.0494702
2026-02-03 16:47:50.049 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.072 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.0721476
2026-02-03 16:47:50.072 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.093 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.0936825
2026-02-03 16:47:50.093 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.116 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.1163356
2026-02-03 16:47:50.116 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.139 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.1390424
2026-02-03 16:47:50.139 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.161 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.1617768
2026-02-03 16:47:50.161 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.184 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.1844585
2026-02-03 16:47:50.184 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.207 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.2071536
2026-02-03 16:47:50.207 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.229 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.2298565
2026-02-03 16:47:50.229 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.252 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.252545
2026-02-03 16:47:50.252 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.275 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.2752285
2026-02-03 16:47:50.275 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.297 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.2978897
2026-02-03 16:47:50.297 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.320 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.3205614
2026-02-03 16:47:50.320 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.343 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.3432524
2026-02-03 16:47:50.343 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.366 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.365998
2026-02-03 16:47:50.366 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.388 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.3885412
2026-02-03 16:47:50.388 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.409 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.4096522
2026-02-03 16:47:50.409 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.431 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.4314897
2026-02-03 16:47:50.431 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.454 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.454311
2026-02-03 16:47:50.454 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.477 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.4770312
2026-02-03 16:47:50.477 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.499 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.4997022
2026-02-03 16:47:50.499 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.522 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.5225527
2026-02-03 16:47:50.522 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.545 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.5452297
2026-02-03 16:47:50.545 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.568 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.5679958
2026-02-03 16:47:50.568 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.590 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.5906742
2026-02-03 16:47:50.590 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.613 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.6133306
2026-02-03 16:47:50.613 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.636 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.6360104
2026-02-03 16:47:50.636 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.658 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.6588812
2026-02-03 16:47:50.658 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.681 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.6815865
2026-02-03 16:47:50.681 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.704 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.7042854
2026-02-03 16:47:50.704 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.727 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.727128
2026-02-03 16:47:50.727 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.749 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.7498233
2026-02-03 16:47:50.749 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.772 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.7724817
2026-02-03 16:47:50.772 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.795 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.7951531
2026-02-03 16:47:50.795 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.817 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.8178332
2026-02-03 16:47:50.817 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.840 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.8405259
2026-02-03 16:47:50.840 | INFO     | __main__:send_wav_file:148 - Sending audio input: 640 bytes, avg_volume: 0.0
2026-02-03 16:47:50.863 | DEBUG    | __main__:send_wav_file:146 - 📍 Silent chunk sent at 1770133670.8633199
2026-02-03 16:47:50.863 | INFO     | __main__:send_wav_file:148 - Sending audio input: 320 bytes, avg_volume: 0.0
2026-02-03 16:47:51.407 | INFO     | pipecat.services.hume.hume:_on_message:266 - custom_session_id=None from_text=False interim=False message=ChatMessage(content='Can you tell me a short sentence?', role='user', tool_call=None, tool_result=None) models=Inference(prosody=ProsodyInference(scores=EmotionScores(admiration=0.00983428955078125, adoration=0.00446319580078125, aesthetic_appreciation=0.004703521728515625, amusement=0.03131103515625, anger=0.06024169921875, anxiety=0.0271148681640625, awe=0.0114593505859375, awkwardness=0.033905029296875, boredom=0.033172607421875, calmness=0.28271484375, concentration=0.2205810546875, confusion=0.2274169921875, contemplation=0.10540771484375, contempt=0.0330810546875, contentment=0.016265869140625, craving=0.0234832763671875, desire=0.00946044921875, determination=0.21533203125, disappointment=0.026641845703125, disgust=0.01189422607421875, distress=0.025115966796875, doubt=0.285400390625, ecstasy=0.00372314453125, embarrassment=0.009063720703125, empathic_pain=0.00716400146484375, entrancement=0.01149749755859375, envy=0.02056884765625, excitement=0.0225067138671875, fear=0.0194854736328125, guilt=0.00469970703125, horror=0.01108551025390625, interest=0.1929931640625, joy=0.004749298095703125, love=0.005123138427734375, nostalgia=0.007015228271484375, pain=0.00800323486328125, pride=0.022857666015625, realization=0.04638671875, relief=0.01412200927734375, romance=0.0076751708984375, sadness=0.0092010498046875, satisfaction=0.01345062255859375, shame=0.005889892578125, surprise_negative=0.09857177734375, surprise_positive=0.01947021484375, sympathy=0.050628662109375, tiredness=0.027801513671875, triumph=0.0065460205078125))) time=MillisecondInterval(begin=148, end=2284) type='user_message' language='ENGLISH'
2026-02-03 16:47:51.408 | INFO     | __main__:process_frame:56 - ⏱️  First transcript latency: 545ms
2026-02-03 16:47:51.408 | INFO     | __main__:process_frame:58 - 👤 User: Can you tell me a short sentence?
2026-02-03 16:47:51.409 | INFO     | pipecat.services.hume.hume:_on_message:258 - custom_session_id=None from_text=False id='1cc49fcf-4799-4923-a14c-3f23c2c2c6f4' message=ChatMessage(content="Alright, I'm Michael Jordan. What's your name, young blood?", role='assistant', tool_call=None, tool_result=None) models=Inference(prosody=None) type='assistant_message' is_quick_response=False language='ENGLISH'
2026-02-03 16:47:51.422 | INFO     | __main__:process_frame:62 - 🤖 Assistant: Alright, I'm Michael Jordan. What's your name, young blood?
2026-02-03 16:47:51.916 | INFO     | pipecat.services.hume.hume:_on_message:248 - Received audio samples from HumeAI id: 1cc49fcf-4799-4923-a14c-3f23c2c2c6f4, 48000.0 samples, channels: 1, duration: 1.0
2026-02-03 16:47:51.916 | SUCCESS  | __main__:process_frame:69 - 🎵 First audio latency: 1053ms
2026-02-03 16:47:52.069 | INFO     | pipecat.services.hume.hume:_on_message:248 - Received audio samples from HumeAI id: 1cc49fcf-4799-4923-a14c-3f23c2c2c6f4, 48000.0 samples, channels: 1, duration: 1.0
2026-02-03 16:47:52.553 | INFO     | pipecat.services.hume.hume:_on_message:248 - Received audio samples from HumeAI id: 1cc49fcf-4799-4923-a14c-3f23c2c2c6f4, 48000.0 samples, channels: 1, duration: 1.0
2026-02-03 16:47:53.620 | INFO     | pipecat.services.hume.hume:_on_message:248 - Received audio samples from HumeAI id: 1cc49fcf-4799-4923-a14c-3f23c2c2c6f4, 43536.0 samples, channels: 1, duration: 0.907
2026-02-03 16:47:55.642 | INFO     | pipecat.services.hume.hume:_on_message:253 - Assistant end for conversation id: 1cc49fcf-4799-4923-a14c-3f23c2c2c6f4