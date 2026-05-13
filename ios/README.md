# Clawdmeter for iPhone SE

このディレクトリは、ESP32 版 Clawdmeter を iPhone SE で動かすための iOS 実装のたたき台です。

重要: これは ESP32 ファームウェアを iPhone に移植するものではありません。iPhone は ESP32 ではないため、`firmware/` の LVGL / Arduino / PlatformIO コードはそのまま動きません。この iOS 版では、iPhone 自体を Claude Code 使用量ダッシュボードとして使います。

## できること

- iPhone SE の画面にセッション使用率・週間使用率を表示する
- 60 秒ごとに Anthropic API を叩いて rate limit ヘッダーを読み取る
- トークンを Keychain に保存する
- ESP32 ボード、PlatformIO、Bluetooth ペアリングなしで使う

## まだできないこと

- ESP32 版の物理ボタン相当の BLE HID キーボード送信
- Clawd ピクセルアニメーションの完全移植
- App Store 配布向けの署名・審査対応
- Claude Code の資格情報を自動で Mac / Linux から読み取ること

## 必要なもの

- Mac
- Xcode
- iPhone SE 実機、または iOS Simulator
- 有効な Claude Code サブスクリプション
- Claude Code の OAuth access token

## Xcode プロジェクトの作り方

このリポジトリには、iOS アプリ本体の Swift ソースを追加しています。Xcode プロジェクトは環境ごとに署名設定が必要になるため、まずはローカルで作成してください。

1. Xcode を開く
2. `File` → `New` → `Project...`
3. `iOS` → `App` を選択
4. Product Name を `ClawdmeteriOS` にする
5. Interface は `SwiftUI`
6. Language は `Swift`
7. Minimum Deployments は、手元の iPhone SE に合わせる
8. 作成されたプロジェクトに、このディレクトリ内の `ClawdmeteriOS/*.swift` を追加する
9. Xcode が作成した初期 `ContentView.swift` と `ClawdmeteriOSApp.swift` は、同名の追加ファイルで置き換える

## トークンの入れ方

アプリを起動すると、トークン入力欄が表示されます。

Claude Code のトークンは通常、PC 側の以下のファイルにあります。

```bash
~/.claude/.credentials.json
```

その中の access token を iPhone アプリに入力して保存します。

注意: この方式は個人利用向けです。トークンは Keychain に保存されますが、他人に配布するアプリでは、ログインフローやトークン管理を正式に設計してください。

## 使い方

1. Xcode でアプリをビルドして iPhone SE に入れる
2. 起動後、Claude Code の access token を保存する
3. `今すぐ更新` を押す
4. 以後はアプリが起動している間、60 秒ごとに自動更新される

## ESP32 版との違い

| 項目 | ESP32 版 | iPhone SE 版 |
| ---- | -------- | ------------ |
| 表示 | 2.16 インチ AMOLED | iPhone SE 画面 |
| 実行環境 | ESP32 + LVGL | iOS + SwiftUI |
| データ取得 | Linux daemon | iPhone アプリ本体 |
| 通信 | daemon → BLE → ESP32 | iPhone → Anthropic API |
| 物理ボタン | あり | なし |
| BLE HID | あり | 未対応 |
| PlatformIO | 必要 | 不要 |

## 今後やるべきこと

1. Xcode プロジェクトを作成して、この Swift ソースを追加する
2. iPhone SE 実機で UI サイズを確認する
3. Claude Code token の取得方法を README にスクリーンショット付きで整理する
4. Clawd アニメーションを iOS 用アセットとして変換する
5. 必要なら App Intents や Shortcuts で簡易操作を追加する
6. BLE HID ボタン相当が本当に必要なら、iOS の制限を確認したうえで別方式を検討する

## iOS 版の設計メモ

- `ClaudeUsageClient.swift` が Anthropic API への通信とヘッダー解析を担当します。
- `KeychainTokenStore.swift` がトークン保存を担当します。
- `ContentView.swift` が iPhone SE 向けの SwiftUI 画面です。
- `ClawdmeteriOSApp.swift` がアプリのエントリーポイントです。
