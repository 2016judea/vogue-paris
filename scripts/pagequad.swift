// Find the page in a scan with Apple's on-device document segmentation model
// (the Notes / Files document scanner). Prints JSON: the quad's four corners in
// normalised coordinates, origin top-left, plus confidence. Falls back to the
// rectangle detector when segmentation finds nothing.
// Build: swiftc -O scripts/pagequad.swift -o bin/pagequad
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOf: URL(fileURLWithPath: path)) else { print("{}"); continue }
  var r = CGRect(origin: .zero, size: img.size)
  guard let cg = img.cgImage(forProposedRect: &r, context: nil, hints: nil) else { print("{}"); continue }
  func emit(_ o: VNRectangleObservation, _ kind: String) {
    func p(_ q: CGPoint) -> [Double] { [Double(q.x), Double(1 - q.y)] }
    let d: [String: Any] = ["kind": kind, "conf": o.confidence, "tl": p(o.topLeft), "tr": p(o.topRight), "br": p(o.bottomRight), "bl": p(o.bottomLeft)]
    if let j = try? JSONSerialization.data(withJSONObject: d), let s = String(data: j, encoding: .utf8) { print(s) }
  }
  let seg = VNDetectDocumentSegmentationRequest()
  let rect = VNDetectRectanglesRequest()
  rect.maximumObservations = 4; rect.minimumAspectRatio = 0.5; rect.maximumAspectRatio = 1.0
  rect.minimumSize = 0.6; rect.quadratureTolerance = 10; rect.minimumConfidence = 0.3
  try? VNImageRequestHandler(cgImage: cg).perform([seg, rect])
  for o in seg.results ?? [] { emit(o, "segment") }
  for o in rect.results ?? [] { emit(o, "rect") }
  print("--")
}
