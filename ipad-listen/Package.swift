{
  "name": "IPadListen",
  "version": "0.1.0",
  "description": "Always-on mic client for homepod-agent",
  "main": "Sources/IPadListen/App.swift",
  "platforms": [
    "iOS",
    "iPadOS"
  ],
  "products": [
    {
      "name": "IPadListen",
      "type": "executable",
      "targets": ["IPadListen"]
    }
  ],
  "targets": [
    {
      "name": "IPadListen",
      "type": "executable",
      "platforms": ["iOS", "iPadOS"],
      "sources": ["Sources/IPadListen/"],
      "info": {
        "NSMicrophoneUsageDescription": "homepod-agent uses the microphone to capture your voice commands.",
        "NSLocalNetworkUsageDescription": "homepod-agent uses your local network to talk to the Mac agent.",
        "NSBonjourServices": [
          "_ipp._tcp",
          "_airplay._tcp"
        ]
      }
    }
  ],
  "swift-tools-version": "5.9"
}