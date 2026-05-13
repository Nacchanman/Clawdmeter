import Foundation

struct ClaudeUsageClient {
    enum ClientError: LocalizedError {
        case missingCredential
        case badResponse
        case requestFailed(Int)

        var errorDescription: String? {
            switch self {
            case .missingCredential:
                return "API credential is empty."
            case .badResponse:
                return "The server response was not readable."
            case .requestFailed(let statusCode):
                return "Request failed with HTTP status \(statusCode)."
            }
        }
    }

    func fetchUsage(credential: String) async throws -> UsageSnapshot {
        let trimmed = credential.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw ClientError.missingCredential }

        var request = URLRequest(url: URL(string: "https://api.anthropic.com/v1/messages")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.setValue("Bearer \(trimmed)", forHTTPHeaderField: "authorization")
        request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        request.httpBody = Data(Self.minimalPayload.utf8)

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ClientError.badResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw ClientError.requestFailed(http.statusCode)
        }

        return UsageSnapshot(
            sessionPercent: Self.headerInt(http, "anthropic-ratelimit-unified-5h-utilization") ?? 0,
            sessionResetMinutes: Self.resetMinutes(http, "anthropic-ratelimit-unified-5h-reset"),
            weeklyPercent: Self.headerInt(http, "anthropic-ratelimit-unified-7d-utilization") ?? 0,
            weeklyResetMinutes: Self.resetMinutes(http, "anthropic-ratelimit-unified-7d-reset"),
            status: "allowed",
            updatedAt: Date(),
            isOK: true
        )
    }

    private static let minimalPayload = """
    {
      "model": "claude-3-5-haiku-latest",
      "max_tokens": 1,
      "messages": [
        { "role": "user", "content": "ping" }
      ]
    }
    """

    private static func headerInt(_ response: HTTPURLResponse, _ name: String) -> Int? {
        guard let value = headerValue(response, name) else { return nil }
        if let intValue = Int(value) { return intValue }
        if let doubleValue = Double(value) { return Int(doubleValue.rounded()) }
        return nil
    }

    private static func resetMinutes(_ response: HTTPURLResponse, _ name: String) -> Int? {
        guard let value = headerValue(response, name) else { return nil }
        if let minutes = Int(value) { return minutes }
        if let seconds = Double(value) { return Int((seconds / 60.0).rounded()) }
        return nil
    }

    private static func headerValue(_ response: HTTPURLResponse, _ name: String) -> String? {
        for (key, value) in response.allHeaderFields {
            guard String(describing: key).lowercased() == name.lowercased() else { continue }
            return String(describing: value)
        }
        return nil
    }
}
