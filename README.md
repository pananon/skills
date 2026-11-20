# skills

Open-sourcing useful, safe and secure agent skills that come in handy every day for a developer.

Each folder is one skill: a `SKILL.md` with the instructions the agent follows, plus any
templates it uses. Copy a skill folder into `~/.claude/skills/` (all projects) or
`<repo>/.claude/skills/` (one project).

| Skill | What it does |
|---|---|
| [expo-ios-app-store](expo-ios-app-store/) | Ship an Expo / React Native app to the Apple App Store with EAS, keeping Android in step and without wasting builds: workflows, pre-build checks, credentials, Sign in with Apple, subscriptions, the App Store Connect listing and an error → fix table. |
| [cs2-clip-finder](cs2-clip-finder/) | Find and cut funny, hype and clutch clips from a 40-60 min CS2 OBS recording at almost zero tokens: local ffmpeg/numpy audio analysis, CS2 Game State Integration events, optional local Whisper + Ollama ranking, then 9:16 captioned renders. |

## License

MIT, see [LICENSE](LICENSE).
