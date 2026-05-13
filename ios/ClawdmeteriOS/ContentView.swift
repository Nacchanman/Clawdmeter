import SwiftUI

struct ContentView: View {
    @StateObject private var settings = LocalSettings()
    @State private var snapshot = UsageSnapshot.placeholder
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var showCredential = false

    private let client = ClaudeUsageClient()
    private let timer = Timer.publish(every: 60, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    header
                    usageGrid
                    credentialSection
                    actionSection
                }
                .padding(16)
            }
            .background(Color.black.ignoresSafeArea())
            .foregroundStyle(.white)
            .navigationTitle("Clawdmeter")
            .navigationBarTitleDisplayMode(.inline)
            .task { await refresh() }
            .onReceive(timer) { _ in Task { await refresh() } }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Claude Code Usage")
                .font(.title2.bold())
            Text("iPhone SE dashboard")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            HStack {
                Circle()
                    .frame(width: 10, height: 10)
                    .foregroundStyle(snapshot.isOK ? .green : .orange)
                Text(snapshot.status)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(snapshot.updatedAt, style: .time)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 22))
    }

    private var usageGrid: some View {
        VStack(spacing: 12) {
            UsageCard(title: "Session", percent: snapshot.sessionPercent, resetText: snapshot.sessionResetText)
            UsageCard(title: "Weekly", percent: snapshot.weeklyPercent, resetText: snapshot.weeklyResetText)
        }
    }

    private var credentialSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("API credential")
                .font(.headline)

            if showCredential {
                TextField("Paste Claude access token", text: $settings.apiCredential)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.caption.monospaced())
                    .padding(12)
                    .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
            } else {
                SecureField("Paste Claude access token", text: $settings.apiCredential)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.caption.monospaced())
                    .padding(12)
                    .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
            }

            Toggle("Show credential", isOn: $showCredential)
                .font(.caption)

            Text("For personal use only. Create a proper login and secure token flow before distributing this app.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 22))
    }

    private var actionSection: some View {
        VStack(spacing: 10) {
            Button {
                Task { await refresh() }
            } label: {
                HStack {
                    if isLoading { ProgressView().tint(.white) }
                    Text(isLoading ? "Updating..." : "Refresh now")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(.white.opacity(0.16), in: RoundedRectangle(cornerRadius: 16))
            }
            .disabled(isLoading)

            Button(role: .destructive) {
                settings.clearCredential()
            } label: {
                Text("Clear credential")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @MainActor
    private func refresh() async {
        guard !settings.apiCredential.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            errorMessage = "Paste your Claude access token first."
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            snapshot = try await client.fetchUsage(credential: settings.apiCredential)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
            snapshot = UsageSnapshot(
                sessionPercent: snapshot.sessionPercent,
                sessionResetMinutes: snapshot.sessionResetMinutes,
                weeklyPercent: snapshot.weeklyPercent,
                weeklyResetMinutes: snapshot.weeklyResetMinutes,
                status: "error",
                updatedAt: Date(),
                isOK: false
            )
        }
    }
}

private struct UsageCard: View {
    let title: String
    let percent: Int
    let resetText: String

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(title)
                    .font(.headline)
                Spacer()
                Text("\(percent)%")
                    .font(.title.bold().monospacedDigit())
            }

            ProgressView(value: Double(min(max(percent, 0), 100)), total: 100)
                .tint(progressTint)

            HStack {
                Text("Reset")
                    .foregroundStyle(.secondary)
                Spacer()
                Text(resetText)
                    .monospacedDigit()
            }
            .font(.caption)
        }
        .padding(18)
        .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 22))
    }

    private var progressTint: Color {
        switch percent {
        case 0..<60: return .green
        case 60..<85: return .yellow
        default: return .orange
        }
    }
}

#Preview {
    ContentView()
}
