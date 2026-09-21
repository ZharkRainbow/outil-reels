// Repere le plus grand visage de chaque image avec Vision (macOS).
// usage : reperer-visage image1.png image2.png ...
// sortie : une ligne par image, "chemin x y l h" en fractions de l'image,
// origine en haut a gauche ; "chemin -" si aucun visage.
import Foundation
import Vision
import AppKit

for chemin in CommandLine.arguments.dropFirst() {
    guard let image = NSImage(contentsOfFile: chemin),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("\(chemin) -"); continue
    }
    let requete = VNDetectFaceRectanglesRequest()
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([requete])
    let visages = (requete.results ?? []).sorted { $0.boundingBox.width > $1.boundingBox.width }
    if let v = visages.first {
        let b = v.boundingBox
        print(String(format: "%@ %.4f %.4f %.4f %.4f", chemin, b.minX, 1 - b.maxY, b.width, b.height))
    } else {
        print("\(chemin) -")
    }
}
