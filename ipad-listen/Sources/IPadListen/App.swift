import Foundation
import AVFoundation

@main
struct IPadListenApp: App {
    @StateObject private var session = MicSession()

    var body: some Scene {
        WindowGroup {
            ContentView(session: session)
        }
    }
}

/// Top-level SwiftUI view. Shows mic status, target server URL, and a single
/// button to start/stop listening.
struct ContentView: View {
    @ObservedObject var session: MicSession

    var body: some View {
        VStack(spacing: 24) {
            Text("homepod-agent — iPad Listen")
                .font(.title)

            HStack(spacing: 12) {
                Circle()
                    .fill(session.isListening ? Color.red : Color.gray)
                    .frame(width: 14, height: 14)
                Text(session.isListening ? "Listening…" : "Idle")
                    .font(.headline)
            }

            TextField("ws://mac-ip:8000/ws/voice", text: $session.serverURL)
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled(true)
                .textInputAutocapitalization(.never)
                .padding(.horizontal, 32)

            Button(session.isListening ? "Stop" : "Start Listening") {
                if session.isListening {
                    session.stop()
                } else {
                    session.start()
                }
            }
            .font(.title2)
            .padding(.horizontal, 32)
            .padding(.vertical, 12)
            .background(session.isListening ? Color.red : Color.green)
            .foregroundColor(.white)
            .clipShape(Capsule())

            if let last = session.lastTranscript {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Last heard:").font(.caption).foregroundColor(.secondary)
                    Text(last).font(.body)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .padding(.horizontal, 32)
            }

            if let reply = session.lastReply {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Agent replied:").font(.caption).foregroundColor(.secondary)
                    Text(reply).font(.body)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(.systemBlue).opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .padding(.horizontal, 32)
            }

            Spacer()

            Text("v0.1 — always-on voice client")
                .font(.footnote)
                .foregroundColor(.secondary)
                .padding(.bottom, 16)
        }
        .padding(.top, 60)
    }
}

/// Manages the AVAudioEngine + WebSocket connection.
///
/// For v0.1 this is a thin client: it captures audio, encodes it as 16kHz
/// mono PCM, and pushes it to the agent. Real ASR can run either on the iPad
/// (via SpeechAnalyzer, iOS 17+) or on the Mac agent (via whisper.cpp).
/// We default to on-Mac ASR for v0.1 — audio is streamed and the agent
/// replies with text. The iPad then plays the reply via AVPlayer.
@MainActor
final class MicSession: NSObject, ObservableObject, URLSessionWebSocketDelegate {
    @Published var isListening: Bool = false
    @Published var serverURL: String = "ws://192.168.178.153:8000/ws/voice"
    @Published var lastTranscript: String? = nil
    @Published var lastReply: String? = nil

    private let engine = AVAudioEngine()
    private var socket: URLSessionWebSocketTask?
    private let session = URLSession(configuration: .default)
    private var seq: UInt64 = 0

    func start() {
        guard !isListening else { return }
        isListening = true

        // Mic permission
        AVAudioApplication.requestRecordPermission { [weak self] granted in
            guard granted else {
                Task { @MainActor in self?.isListening = false }
                return
            }
            Task { @MainActor in
                self?.connect()
                self?.startEngine()
            }
        }
    }

    func stop() {
        engine.stop()
        socket?.cancel(with: .normalClosure, reason: nil)
        socket = nil
        isListening = false
    }

    private func connect() {
        guard let url = URL(string: serverURL) else { return }
        let task = session.webSocketTask(with: url)
        task.delegate = self
        socket = task
        task.resume()
        listen()
    }

    private func listen() {
        socket?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure:
                return
            case .success(let msg):
                self.handle(msg)
                self.listen()
            }
        }
    }

    private func handle(_ msg: URLSessionWebSocketTask.Message) {
        guard case .string(let text) = msg,
              let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }
        let type = obj["type"] as? String ?? ""
        if type == "reply",
           let payload = obj["payload"] as? [String: Any],
           let reply = payload["reply"] as? String {
            Task { @MainActor in self.lastReply = reply }
        }
    }

    private func startEngine() {
        let input = engine.inputNode
        let format = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 16000,
            channels: 1,
            interleaved: true
        )
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.pushAudio(buffer: buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            stop()
        }
    }

    private func pushAudio(buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.int16ChannelData else { return }
        let frameLength = Int(buffer.frameLength)
        let data = Data(bytes: channelData[0], count: frameLength * 2)
        let msg: [String: Any] = [
            "type": "audio",
            "seq": seq,
            "format": "pcm16le-16khz-mono",
            "data": data.base64EncodedString(),
        ]
        seq += 1
        guard let json = try? JSONSerialization.data(withJSONObject: msg) else { return }
        socket?.send(.data(json)) { _ in }
    }

    nonisolated func urlSession(_ session: URLSession,
                                webSocketTask: URLSessionWebSocketTask,
                                didOpenWithProtocol protocol: String?) {
        // Send a config frame so the agent knows who we are.
        let msg: [String: Any] = [
            "type": "config",
            "device": "iPadListen/0.1",
            "asr_model": "remote",  // the Mac agent does ASR for v0.1
        ]
        if let data = try? JSONSerialization.data(withJSONObject: msg),
           let str = String(data: data, encoding: .utf8) {
            webSocketTask.send(.string(str)) { _ in }
        }
    }
}