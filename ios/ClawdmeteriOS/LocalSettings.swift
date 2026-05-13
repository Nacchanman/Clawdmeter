import Foundation

final class LocalSettings: ObservableObject {
    @Published var apiCredential: String {
        didSet { UserDefaults.standard.set(apiCredential, forKey: Self.credentialKey) }
    }

    private static let credentialKey = "clawdmeter.apiCredential"

    init() {
        self.apiCredential = UserDefaults.standard.string(forKey: Self.credentialKey) ?? ""
    }

    func clearCredential() {
        apiCredential = ""
        UserDefaults.standard.removeObject(forKey: Self.credentialKey)
    }
}
