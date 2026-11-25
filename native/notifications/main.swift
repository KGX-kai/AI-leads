import AppKit
import CoreServices
import UserNotifications

let destination = URL(string: "http://127.0.0.1:8765/notifications")!
let center = UNUserNotificationCenter.current()
let args = Array(CommandLine.arguments.dropFirst())
func reply(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    }
    DispatchQueue.main.async { NSApplication.shared.terminate(nil) }
}
func statusName(_ status: UNAuthorizationStatus) -> String {
    switch status {
    case .notDetermined: return "not_determined"
    case .denied: return "denied"
    case .authorized: return "authorized"
    case .provisional: return "provisional"
    @unknown default: return "unknown"
    }
}
func settings(_ s: UNNotificationSettings) -> [String: Any] {
    return ["authorization": statusName(s.authorizationStatus), "alert_setting": s.alertSetting.rawValue,
            "notification_center_setting": s.notificationCenterSetting.rawValue]
}
func runCommand() {
    guard let command = args.first else { return }
    switch command {
    case "status": center.getNotificationSettings { reply(settings($0)) }
    case "request":
        center.requestAuthorization(options: [.alert]) { _, error in
            if let error = error as NSError? {
                reply(["error": "authorization_error", "code": error.code]); return
            }
            center.getNotificationSettings { reply(settings($0)) }
        }
    case "delivered":
        center.getDeliveredNotifications { items in
            reply(["present_in_notification_center": items.map { ["event_id": $0.request.identifier, "delivered_at": $0.date.timeIntervalSince1970] as [String: Any] }])
        }
    case "notify":
        guard args.count == 3,
              args[1].range(of: "^[A-Za-z0-9_-]{1,128}$", options: .regularExpression) != nil,
              let count = Int(args[2]), (1...999999).contains(count) else {
            reply(["error": "invalid_arguments"]); return
        }
        center.getNotificationSettings { s in
            guard s.authorizationStatus == .authorized || s.authorizationStatus == .provisional else {
                reply(["error": "notification_not_authorized", "authorization": statusName(s.authorizationStatus)]); return
            }
            let content = UNMutableNotificationContent()
            content.title = "京小电获客提醒"
            content.body = "有 \(count) 项事项需要你查看"
            content.userInfo = ["event_id": args[1]]
            center.add(UNNotificationRequest(identifier: args[1], content: content, trigger: nil)) { error in
                if let error = error as NSError? {
                    reply(["error": "submission_failed", "code": error.code])
                } else { reply(["status": "accepted", "event_id": args[1]]) }
            }
        }
    default: reply(["error": "unknown_command"])
    }
}
final class Delegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationWillFinishLaunching(_ notification: Notification) {
        center.delegate = self
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        LSRegisterURL(Bundle.main.bundleURL as CFURL, true)
        runCommand()
        // A system notification click may launch the app without arguments.
        // Leave time for didReceive; do not request permission or send by default.
        if args.isEmpty {
            DispatchQueue.main.asyncAfter(deadline: .now() + 20) { NSApplication.shared.terminate(nil) }
        }
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
        withCompletionHandler completion: @escaping (UNNotificationPresentationOptions) -> Void) {
        completion([.banner, .list])
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
        withCompletionHandler completion: @escaping () -> Void) {
        DispatchQueue.main.async {
            if response.actionIdentifier == UNNotificationDefaultActionIdentifier { NSWorkspace.shared.open(destination) }
            completion()
            if args.isEmpty { NSApplication.shared.terminate(nil) }
        }
    }
}
let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
