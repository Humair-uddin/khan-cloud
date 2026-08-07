# Khan Cloud Control Plane UI

Frontend Operations Dashboard v1 is a dependency-light static web client for the Khan Cloud Control Plane.

## Runtime

Serve this directory from the same origin as the Control Plane API, or set an alternate API base from the login screen.

The UI stores only the bearer access token and API base in browser localStorage. It does not store passwords.

## Features

- Control Plane login
- Fleet/deployment health summary cards
- Deployment status table
- Prioritized support/operations attention queue
- Auto refresh (30 seconds)
- Manual refresh and logout
- Same-origin API by default

## Tests

```bash
npm test
```
