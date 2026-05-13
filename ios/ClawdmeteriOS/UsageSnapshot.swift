import Foundation

struct UsageSnapshot: Equatable {
    var sessionPercent: Int
    var sessionResetMinutes: Int?
    var weeklyPercent: Int
    var weeklyResetMinutes: Int?
    var status: String
    var updatedAt: Date
    var isOK: Bool

    static let placeholder = UsageSnapshot(
        sessionPercent: 0,
        sessionResetMinutes: nil,
        weeklyPercent: 0,
        weeklyResetMinutes: nil,
        status: "Not loaded",
        updatedAt: Date(),
        isOK: false
    )
}

extension UsageSnapshot {
    var sessionResetText: String {
        guard let sessionResetMinutes else { return "--" }
        return Self.formatMinutes(sessionResetMinutes)
    }

    var weeklyResetText: String {
        guard let weeklyResetMinutes else { return "--" }
        return Self.formatMinutes(weeklyResetMinutes)
    }

    private static func formatMinutes(_ minutes: Int) -> String {
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let mins = minutes % 60
        if mins == 0 { return "\(hours) h" }
        return "\(hours) h \(mins) min"
    }
}
