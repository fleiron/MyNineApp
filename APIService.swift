


import Foundation

final class APIService {
    static let shared = APIService()
    // TODO: replace with your HF Space URL
    private let baseURL = URL(string: "https://ilyabnae-mynineapp.hf.space")!

    func generate(req: GenerateRequest) async throws -> GenerateResponse {
        var url = baseURL.appending(path: "/generate_reply")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json",forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(req)

        let (data, resp) = try await URLSession.shared.data(for: request)
        guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw NSError(domain: "api", code: (resp as? HTTPURLResponse)?.statusCode ?? 0, userInfo: [NSLocalizedDescriptionKey: body])
        }
        return try JSONDecoder().decode(GenerateResponse.self, from: data)
    }

    func feedback(generationId: String, chosen: ReplyOption?) async {
        let url = baseURL.appending(path: "/feedback")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.addValue("application/json",forHTTPHeaderField: "Content-Type")
        let payload: [String: Any] = [
            "generation_id": generationId,
            "chosen_label": chosen?.label as Any,
            "chosen_text": chosen?.text as Any,
            "liked": true
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        _ = try? await URLSession.shared.data(for: req)
    }
}
