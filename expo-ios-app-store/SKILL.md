---
name: expo-ios-app-store
description: Ship an Expo / React Native app to the Apple App Store with EAS, keeping Android in step and without wasting builds. Use when someone wants to put an Expo app on iOS or the App Store, set up iOS credentials, run an iOS EAS build or submit, fill in the App Store Connect listing (screenshots, App Privacy, review notes), add Sign in with Apple or App Store subscriptions, or fix an App Store rejection or iOS build error.
---

# Expo app → Apple App Store

A checklist for taking an Expo (EAS) app that already ships on Android to the App Store. Most of
the work is free: config checks, credentials and listing work. Builds are the scarce part. Find
every problem before the first iOS build.

## 0. Ground rules

- **No EAS build until the user says "build"** in the session.
- **Builds come from a shared quota.** The EAS quota belongs to the Expo account or organisation
  in the app's `owner` field, and every project under that owner shares it. It resets on the 1st
  of each month. Free plans give a small count per platform (15 Android + 15 iOS at the time of
  writing). Builds that error out are often not counted. Ask the user to check expo.dev → owner
  → Billing before each build, and say how many are left.
- **One platform at a time** (`-p ios`). Never use `all`, especially while one platform is out of
  quota or failing.
- **Re-submitting costs nothing.** `eas submit --id <build-id>` re-sends a finished build and uses
  no build, so prefer it to rebuilding.
- **Pushes and merges must not build.** Make build workflows manual-only before anything else
  (section 1). Until that change is on the default branch, put `[eas skip]` in every commit
  message (`[skip eas]` and `[no eas]` work too).
- **Production only with an explicit go:** App Store submission / Add for Review, a Play rollout,
  and writes to a production database (section 12).
- **Build from a clean, intended commit.** EAS uploads the folder you run it from, including
  uncommitted files. If the main checkout has unrelated work in progress, build from a separate
  worktree:
  ```bash
  git worktree add ../app-ios <branch>
  ```
  Then run `npm ci` there. Don't commit, discard or stash someone else's uncommitted work.
- **Never type the user's Apple or Google passwords or 2FA codes.** The owner runs interactive
  `eas` commands (credentials, first submit), and you say what to pick at each prompt.
- **Use the latest eas-cli:** `npx eas-cli@latest …`. Old versions fail with errors like "iTunes
  service key is empty" or loop on Apple login.
- **Windows:** use `npx.cmd`, not `npx`. PowerShell blocks `npx.ps1` with "running scripts is
  disabled".

## 1. Stop accidental builds (EAS Workflows)

Look in `.eas/workflows/*.yml` for `on: push` / `pull_request` triggers that build. Replace them
with a `workflow_dispatch` that has a platform choice input, job-level `if:` conditions and
independent per-platform chains. A template is in `templates/production-builds.yml`.

- Job ids: use **underscores** (`build_ios`), never hyphens. A hyphenated id breaks
  `${{ needs.<id>.outputs.build_id }}` expressions; submit fails with errors like "Invalid
  identifier android".
- Keep the chains separate (`build_ios → submit_ios`, `build_android → submit_android`). When
  they're coupled, an Android failure or empty Android quota silently skips the iOS submit.
- Validate the YAML before committing with the Expo MCP `workflow_validate` tool.
- **Expo dashboard GitHub build triggers are separate from workflow files.** Check expo.dev →
  project → GitHub and turn them off there too.
- To verify that nothing built after a push, list recent builds (Expo MCP `build_list` or
  `eas build:list`).
- Run the workflow with
  ```bash
  npx eas-cli workflow:run .eas/workflows/production-builds.yml -F platform=ios
  ```

## 2. Free pre-build checks (run all, fix all)

```bash
npx expo-doctor
npx tsc --noEmit
npm run lint
npx expo export --platform ios
npx expo config --type introspect --json
```

- `expo-doctor` failing only on patch versions: `npx expo install --fix`.
- `expo export --platform ios` proves the JS bundle builds for iOS. The output should list an
  `ios` bundle. It also shows whether `EXPO_PUBLIC_*` values from `.env` were inlined: grep the
  bundle for a value you expect.
- **Introspect works on Windows** and runs the iOS config plugins. `expo prebuild -p ios`
  doesn't, so introspect is how you see the real Info.plist and entitlements before building.
- Lint errors from `react-hooks/rules-of-hooks` are real crash bugs (a hook after an early
  return). Fix them. Most other React Compiler lint rules can wait.

**Lockfile check (free, catches a common EAS install failure).** Windows `npm install` can drop
optional wasm dependencies that macOS/Linux need. EAS then fails with "Missing: @emnapi/core@x
from lock file". Catch it before building: copy `package.json` and `package-lock.json` to a
scratch folder and replay the install for the build platforms:

```bash
npm ci --dry-run --os=darwin --cpu=arm64
```

Use npm 10 for that one, then run this with the latest npm:

```bash
npm ci --dry-run --os=linux --cpu=x64
```

To fix it, copy the missing `node_modules/@emnapi/*` (or similar) entries back from the default
branch's lockfile, or from a lockfile made on macOS or Linux. `npm install --package-lock-only`
on Windows won't add them back.

Read the introspected `ios` block and check:

| Key | Want |
|---|---|
| `bundleIdentifier` | Your real id. `com.placeholder.appid` means it's missing. |
| `infoPlist.ITSAppUsesNonExemptEncryption` | `false` (from `ios.config.usesNonExemptEncryption`), unless the app really uses non-exempt encryption. Without it, every build waits on "Missing Compliance". |
| `infoPlist.UISupportedInterfaceOrientations` | Portrait only, if the app is designed for portrait (`"orientation": "portrait"`). |
| `infoPlist.UIRequiresFullScreen` / `~ipad` keys | Present only if you support iPad. |
| `infoPlist.UIBackgroundModes` | Only the modes the app really uses. Review asks about each one. |
| `infoPlist.CFBundleURLTypes` | Your scheme, plus the reversed Google client id if Google sign-in is on iOS. |
| `NS*UsageDescription` keys | One for every API a linked library *references* (section 3). |
| `entitlements` | Exactly the capabilities the provisioning profile must contain: `com.apple.developer.applesignin`, `aps-environment`, `com.apple.developer.healthkit`… If any appeared since the last iOS build, delete the profile first (section 7b). `aps-environment: development` here is normal: the distribution profile signs it as production. |

## 3. `app.json` iOS block

```json
"orientation": "portrait",
"ios": {
  "bundleIdentifier": "com.example.app",
  "supportsTablet": false,
  "usesAppleSignIn": true,
  "config": { "usesNonExemptEncryption": false }
}
```

- **Bundle id:** usually the same as the Android package. It must match the App Store Connect app.
- **`supportsTablet`:** `false` unless the user wants iPad screenshots and iPad review. With
  `false`, the app still runs on iPad in iPhone mode. Ask.
- **Orientation:** the top-level `orientation` also changes Android. Say so before changing it.
- **Purpose strings:** Apple's ITMS-90683 check **scans the binary, not your code**. Every API a
  linked library references needs its usage string, even if the app never calls it. Set them in
  each module's config plugin options where possible, otherwise in `ios.infoPlist`. Write them
  plainly ("Used to read your workouts from Apple Health"). App Review reads them and rejects
  vague text. Common ones:

  | Module | Keys |
  |---|---|
  | expo-camera, expo-image-picker (camera) | `NSCameraUsageDescription` |
  | expo-image-picker, expo-media-library | `NSPhotoLibraryUsageDescription`, `NSPhotoLibraryAddUsageDescription` |
  | microphone (expo-camera video, expo-audio/expo-av recording) | `NSMicrophoneUsageDescription` |
  | expo-location | `NSLocationWhenInUseUsageDescription` (+ `Always…` only if needed) |
  | expo-contacts | `NSContactsUsageDescription` |
  | expo-calendar | `NSCalendarsUsageDescription` / `NSRemindersUsageDescription` |
  | expo-local-authentication | `NSFaceIDUsageDescription` |
  | expo-tracking-transparency | `NSUserTrackingUsageDescription` |
  | HealthKit libraries | **both** `NSHealthShareUsageDescription` and `NSHealthUpdateUsageDescription`, even for read-only use |

  expo-notifications needs no purpose string.

**Committed native folders.** If `ios/` or `android/` is committed and *not* excluded by
`.easignore` (or `.gitignore`, when there is no `.easignore`), EAS builds it as-is, and
`app.json` changes for that platform need `npx expo prebuild` or a manual edit. If they're
excluded, EAS regenerates them from `app.json`, which is the simpler setup. Check before
assuming either.

## 4. Sign-in

- **Guideline 4.8:** if the iOS app offers a third-party or social login (Google, Facebook…), it
  must also offer **Sign in with Apple**. If iOS offers only email/password, 4.8 doesn't apply.
  Check the code: some apps gate Google sign-in to Android only.
- **Sign in with Apple:** use `expo-apple-authentication` (add it to `plugins`) and
  `ios.usesAppleSignIn: true`. Show Apple's own `AppleAuthenticationButton`, and only when
  `isAvailableAsync()` is true. Exchange the `identityToken` with your backend (Supabase:
  `signInWithIdToken({ provider: 'apple', token })`; turn on the Apple provider and put the
  bundle id in its Client IDs). The App ID needs the Sign in with Apple capability; if it's
  added after an earlier iOS build, delete the profile (section 7b). "Hide My Email" gives a
  relay address, so it won't link to an existing email account.
- **Google sign-in on iOS** (`@react-native-google-signin/google-signin`):
  - Needs an **iOS** OAuth client (Google Cloud → Credentials → OAuth client ID → iOS, with the
    bundle id).
  - Pass `iosClientId` to `GoogleSignin.configure`, and skip `hasPlayServices()` on iOS.
  - Register the reversed client id as a URL scheme, normally the plugin's `iosUrlScheme` (in
    non-Firebase mode the plugin throws at prebuild without one). Without changing the plugin
    mode (for example when Android relies on its Firebase mode), put it in `ios.scheme` instead.
  - Add the iOS client id to the backend's accepted Google client ids (Supabase: Google provider
    → Client IDs, comma-separated). Otherwise sign-in fails with an audience error.
- **Dev-only logins never ship.** Gate test email/password shortcuts with `__DEV__`.
- **Account deletion (5.1.1(v)):** an app that lets users create accounts must let them delete
  them in the app. For Sign in with Apple users, Apple also expects the app to revoke the Apple
  token (REST `auth/revoke`) on deletion. Ask the user whether to build it before review.

## 5. Push notifications

- A push key (APNs) is needed **only if a server sends pushes**. Local scheduled notifications
  need none.
- `eas credentials -p ios` can create the APNs key and store it.
- Check how the backend sends pushes before promising they work on iOS:
  - **Expo Push API** (`exp.host/--/api/v2/push/send`, `ExponentPushToken[…]` tokens): works on
    iOS once EAS has the APNs key. No server change is needed.
  - **FCM directly** (Firebase Admin with device tokens): iOS also needs a Firebase iOS app, the
    APNs key uploaded to Firebase, and `GoogleService-Info.plist` (`ios.googleServicesFile`).
  - Custom APNs code: needs the key on the server.
- `getExpoPushTokenAsync` needs the EAS `projectId` (from `extra.eas.projectId`).

## 6. In-app purchases and subscriptions

- **Guideline 3.1.1:** digital goods and features sold in an iOS app must use Apple IAP. On iOS,
  never show "buy on Google Play" or "pay on our website" links, Play-only promo codes or offer
  ids, or a paywall whose purchase can't complete.
- Make store wording and links platform-aware ("Manage in the App Store" →
  `https://apps.apple.com/account/subscriptions`), and gate Play-only features (offer ids, promo
  codes mapped to Play offers) to Android.
- **Guideline 3.1.2:** the paywall must show price and period, and link to **Terms of Use**
  (Apple's standard EULA, https://www.apple.com/legal/internet-services/itunes/dev/stdeula/, or
  your own) and the **Privacy Policy**. Include a **Restore purchases** button.
- **App Store Connect setup:**
  - The **Paid Applications agreement** must be active, with bank and tax done.
  - Create a subscription group and products. Reusing the Play product ids keeps things simple.
  - Each product needs a localization and a review screenshot.
  - **Attach the subscriptions to the app version** before the first review. They're reviewed
    together.
- **RevenueCat:**
  - Add the App Store app to the *same* project.
  - Upload an In-App Purchase key (.p8 + Key ID + Issuer ID). Keep the .p8 out of the repo.
  - Attach the iOS products to the same entitlement and to the same offering packages.
  - Paste RevenueCat's Apple server-notification URL into App Store Connect (Production and
    Sandbox, Version 2).
  - Set the `appl_…` public SDK key in the app config.
  - Check that webhooks are project-wide and handle sandbox events.
- **Sandbox testers** live in App Store Connect → Users and Access → Sandbox. App Review buys in
  the sandbox too.

## 7. Credentials

The owner runs it, because it's interactive:

```bash
npx eas-cli@latest credentials -p ios
```

- Pick the **production** build profile.
- **Distribution certificate:** reuse the existing one, and never revoke it. Apple allows only a
  few per team.
- **"Generate a new App Store Connect API Key?"**: Yes, with the Admin or App Manager role. EAS
  stores it, and later submits run non-interactively.
- **Push key (APNs):** only if a server sends pushes (section 5). Let EAS create it, or reuse the
  team's existing key (one key serves all the team's apps).
- **Provisioning profile:** let EAS manage it.

### 7b. Capabilities changed → delete the provisioning profile

A profile is generated with the App ID's capabilities at that moment. Add a capability later
(HealthKit, Sign in with Apple, push, App Groups…) and the build fails with errors like
"Provisioning profile doesn't include the … capability". Delete the profile:
1. Run `eas credentials -p ios` → production → Build Credentials → Provisioning Profile → Delete.
2. Let it delete the profile on Apple's side too.
3. **Leave the distribution certificate.**

The next build regenerates the profile with the current capabilities.

## 8. `eas.json`

```json
"cli": { "appVersionSource": "remote" },
"build": { "production": { "autoIncrement": true } },
"submit": { "production": { "ios": { "ascAppId": "<App Store Connect Apple ID>", "appleTeamId": "<Team ID>" } } }
```

- `ascAppId` is the numeric **Apple ID** in App Store Connect → app → App Information. Create the
  App Store Connect app first: Apps → + → New App, with platform iOS, the bundle id and an SKU.
- Keep `appVersionSource: remote` + `autoIncrement` so build numbers never collide.
- `EXPO_PUBLIC_*` values come from `.env` files that EAS uploads, or from EAS environment
  variables for the build's environment. Don't put secrets in either: `EXPO_PUBLIC_*` values are
  inlined into the app.

## 9. Build and submit (only after "build")

```bash
npx eas-cli@latest build -p ios --profile production --auto-submit
```

- Re-run section 2 on the exact commit, from the exact folder you'll build from.
- After the build, check its `gitCommitHash` (`eas build:view` or the Expo MCP `build_info`)
  matches the commit you meant to ship. A build with old code usually means eas ran in another
  worktree.
- If the build fails, read the failing phase's logs (`eas build:view`, or the Expo MCP
  `build_logs`), fix the cause, re-run the free checks, and ask before rebuilding.
- **After upload:**
  - Apple emails any ITMS rejection within about 15 minutes; otherwise processing takes
    5–30 minutes, then the build appears in TestFlight and on the version page.
  - A rejected binary can't be reused. Fix the cause and build again; autoIncrement gives it the
    next build number.

## 10. App Store Connect listing

- **Screenshots:**
  - Field-tested in late 2026: **1206 × 2622** or **1179 × 2556** portrait were accepted, while
    the older 6.5" size failed with "File dimensions are invalid". Check Apple's "Screenshot
    specifications" page if it rejects these.
  - Use real app screens (marketing frames are fine), with no Android status bars or Play badges.
  - iPad sizes only if `supportsTablet`.
- **Header asset (optional):** 3840 × 1646 or 5244 × 2950. Keep key content centred and the
  bottom quiet: the App Store draws the app name and Get button there.
- **App Privacy:**
  - Declare what the app and its SDKs collect. Go by what the code sends. Examples:
    - auth email → Contact Info / Email
    - user id → Identifiers
    - purchases via RevenueCat → Purchases
    - health data → Health & Fitness
    - crash and analytics SDKs → Diagnostics / Usage
    - records the user types in → Other User Content
  - For a typical app with accounts, mark every type as linked to the user, used for App
    Functionality, and not used for tracking (unless the app has ATT).
  - Then press **Publish**. A saved but unpublished App Privacy section blocks submission.
- **Privacy policy URL:** required. Check that it loads. If the app uses HealthKit, the policy
  must describe Health data.
- **China mainland:** untick it (Pricing and Availability → App Availability → Manage
  Availability) unless you have an ICP filing. Leaving it on brings Security Assessment / AIGC
  banners, and review stalls.
- **Age rating questionnaire**, category, support URL, copyright.
- **Review notes:** say exactly how to sign in. Provide a working **demo account** with realistic
  sample data, or note that Sign in with Apple gets the reviewer in, if a new account shows
  enough. Give the steps to reach each paid feature and the subscription screen, and note any
  feature that's region- or server-gated.
- **Version page:** pick the build, attach the subscriptions, set export compliance (automatic
  when `ITSAppUsesNonExemptEncryption` is false), then **Add for Review** → Submit, only with the
  user's go.

## 11. Keep Android in step (Google Play)

- Shared changes (new native modules, `orientation`, version) reach Android only in its next
  build. Build Android separately, after iOS is sorted, and roll it out on Play only with a go.
- New native modules may need Android permissions. Check any manifest-stripping config plugin's
  allowlist.
- Without a Play service-account key on EAS, `eas submit -p android` can't run
  non-interactively. Either the owner uploads the .aab by hand, or you add the key to EAS once.
- **Play declarations:**
  - Health Connect apps need the Health apps declaration (list only the read permissions
    actually used) and Data safety → Health and fitness info.
  - Background location needs the location permissions declaration and a demo video.
- **Play listing sizes:** feature graphic 1024 × 500; phone screenshots 1080 × 1920 work.

## 12. Production data changes

When the release needs a live database change (backfills, config rows, new columns), write it as
a SQL file **the owner runs**. Never run it yourself. The file must be:
- **One transaction**, with guard checks that `raise exception` if anything looks unexpected
  (row counts, existing values), so nothing is saved on a surprise.
- **Additive only** and **safe to run twice** (`if not exists`, `on conflict do nothing`).
- Ended with a **verification `select`** that shows the result.
- **Tested first** on a local Postgres (for example PGlite) with the repo's migrations applied.

## 13. Error → fix

| Symptom | Cause | Fix |
|---|---|---|
| "Missing Compliance" on every build | No encryption flag | `ios.config.usesNonExemptEncryption: false` |
| Email ITMS-90683 "Missing purpose string" | A linked library references an API with no usage string (Apple scans the binary) | Add the string (section 3), re-run introspect |
| Provisioning profile "doesn't include the … capability" (HealthKit, Sign in with Apple…) | Profile made before the capability was added | Delete the profile (7b); the next build regenerates it |
| "iTunes service key is empty" / endless Apple login loop | Old eas-cli | `npx eas-cli@latest` |
| `npx`: "running scripts is disabled" (PowerShell) | `npx.ps1` blocked by execution policy | Use `npx.cmd` |
| EAS install: "Missing: @emnapi/core@x from lock file" | Windows npm dropped optional wasm deps from the lockfile | Restore the entries from a macOS/Linux lockfile; catch it with the `npm ci --dry-run --os/--cpu` replay (section 2) |
| Workflow submit: "Invalid identifier android" (or similar) | Hyphenated job id in `needs.<id>` expressions | Underscores in job ids |
| iOS submit skipped after the Android build failed | Coupled jobs / Android quota used up | Independent chains; build one platform |
| Build contains old code | `eas` ran from another folder or worktree | Run from the intended folder; check the build's `gitCommitHash` |
| Screenshots: "File dimensions are invalid" | Old 6.5" size | 1206 × 2622 or 1179 × 2556 |
| Security Assessment / AIGC banners in App Store Connect | Available in China mainland | Untick China mainland |
| Workflow built on push / merge | Push/PR trigger in the YAML, or a dashboard GitHub trigger | `workflow_dispatch` only; turn off dashboard triggers; `[eas skip]` |
| Duplicate build number on upload | Local version source / no auto-increment | `appVersionSource: remote` + `autoIncrement: true` |
| Distribution certificate limit reached | New certificate created per build/machine | Reuse the existing certificate; never revoke it |
| Bundle id shows `com.placeholder.appid` | `ios.bundleIdentifier` not set | Set it to match App Store Connect |
| Prebuild error: google-signin "Missing `iosUrlScheme`" | Plugin in non-Firebase mode without the iOS scheme | Pass `iosUrlScheme` (reversed iOS client id), or keep Firebase mode and use `ios.scheme` |
| Google sign-in on iOS crashes or doesn't return to the app | Reversed client id missing from URL schemes, or no `iosClientId` | Add both (section 4) |
| Backend rejects the Google/Apple token (audience / invalid client) | iOS client id or bundle id not in the provider's accepted ids | Add the iOS client id (Google) or bundle id (Apple) |
| Pushes work on Android, not iOS | No APNs key | Create it in EAS credentials (and upload it to Firebase if sending via FCM) |
| Rejected 4.8 (login services) | Google/social login without Sign in with Apple | Add Sign in with Apple, or remove the third-party login on iOS |
| Rejected 3.1.1 (payments) | External purchase links or Play-only flows on iOS | Remove them on iOS; sell via IAP |
| Rejected 3.1.2 (subscriptions) | Missing Terms/Privacy links, price/period or Restore | Add them to the paywall |
| Rejected 2.1 (information needed / can't sign in) | Reviewer couldn't sign in or reach features | Demo account with data, sign-in steps in the review notes; check the backend is up and not region-blocked |
| Rejected 5.1.1(v) (account deletion) | No in-app account deletion | Add it; revoke Sign in with Apple tokens |
| Rejected 2.3.x (metadata / screenshots) | Other platforms' names or badges, or non-app screens | Real iOS screens only |
| Subscriptions "not submitted" / IAP missing in review | Not attached to the version, or metadata missing | Attach them; fill in localization + review screenshot |
| Submission blocked on App Privacy | Answers saved but not published | Press Publish in App Privacy |

## 14. Handoffs between sessions

Work like this spans days and several sessions. Keep a short status note in the repo (what's
done, IDs that aren't secret, what's left, the exact next step) and update it at each
milestone. Never write API keys, .p8 files or passwords into it.
