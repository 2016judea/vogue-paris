// On-device OCR with Apple Vision (the Live Text engine). Prints one JSON line per
// recognised text line: {"t": text, "x","y","w","h": normalised box, origin top-left}.
// Build: swiftc -O scripts/ocr.swift -o bin/ocr
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOf: URL(fileURLWithPath: path)) else { continue }
  var r = CGRect(origin: .zero, size: img.size)
  guard let cg = img.cgImage(forProposedRect: &r, context: nil, hints: nil) else { continue }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.recognitionLanguages = ["fr-FR"]
  req.usesLanguageCorrection = true
  try? VNImageRequestHandler(cgImage: cg).perform([req])
  for o in req.results ?? [] {
    guard let c = o.topCandidates(1).first else { continue }
    let b = o.boundingBox
    let d: [String: Any] = ["t": c.string, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height]
    if let j = try? JSONSerialization.data(withJSONObject: d), let s = String(data: j, encoding: .utf8) { print(s) }
  }
}
