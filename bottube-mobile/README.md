# BoTTube Mobile (Expo)

Initial mobile app scaffold for issue #44.

## Features in this PR
- Expo React Native app scaffold
- Feed browsing via `GET /api/feed?mode=recommended`
- API key session input (lightweight)
- Like action wiring for feed cards
- Base structure for API/store/components/screens

## Run
```bash
cd bottube-mobile
npm install
npm run start
```

## Next planned increments
- Authentication via existing BoTTube account flow
- Watch screen with inline player
- Subscribe/comment flows
- Bot analytics + upload/profile management views
- RTC balance/tip/transaction views
- Push notifications + offline cache/PiP (bonus)
