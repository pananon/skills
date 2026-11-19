# expo-ios-app-store

An agent skill for shipping an **Expo / React Native app to the Apple App Store with EAS**,
keeping Android in step and without wasting builds on a small build quota.

It covers:
- making EAS Workflows manual-only, so pushes don't burn builds
- the free pre-build checks (expo-doctor, type-check, `expo export --platform ios`, config introspection)
- the `app.json` iOS block and purpose strings
- Sign in with Apple and Google sign-in on iOS (guideline 4.8)
- push notifications (APNs)
- App Store subscriptions with RevenueCat (guidelines 3.1.1 / 3.1.2)
- EAS credentials and `eas.json` submit config
- the App Store Connect listing (screenshots, App Privacy, China mainland, review notes) and Google Play declarations
- the lockfile check that catches a common EAS install failure, and safe production SQL changes
- an error → fix table for build, credential, workflow, lockfile and review errors

## Install

Copy this folder into your skills directory:

- Claude Code, for all projects: `~/.claude/skills/expo-ios-app-store/`
- Claude Code, for one project: `<repo>/.claude/skills/expo-ios-app-store/`

Then ask something like "put this app on the App Store" or "load the expo-ios-app-store skill".

## Contents

- `SKILL.md`: the checklist the agent follows
- `templates/production-builds.yml`: a manual-dispatch EAS workflow with independent iOS and Android build→submit chains

## Notes

App Store rules, screenshot sizes and Expo/EAS options change. The skill tells the agent to
check current Apple and Expo docs where details move. Corrections and PRs welcome.

## License

MIT, see [LICENSE](../LICENSE).
