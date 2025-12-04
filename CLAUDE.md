# CLAUDE.md - AI Assistant Guide for zk-2048

## Project Overview

This is **zk-2048**, a zero-knowledge proof-enabled implementation of the classic 2048 puzzle game. The game runs off-chain using WebAssembly (WASM) and allows players to submit cryptographic proofs of their gameplay to the blockchain for on-chain verification and rewards redemption.

The project is part of the zkCross/Delphinus Labs ecosystem, leveraging zkWASM technology to generate zero-knowledge proofs of game state transitions.

## Technology Stack

- **Language**: TypeScript 4.x
- **Frontend Framework**: React 18
- **State Management**: Redux Toolkit (RTK)
- **UI Components**: React Bootstrap v2, Bootswatch (Slate theme)
- **Styling**: SCSS, Bootstrap 5
- **Build Tool**: react-app-rewired (Create React App with custom config)
- **Game Logic**: C compiled to WebAssembly
- **Blockchain**: Ethereum-compatible (Goerli testnet configured)
- **ZK Proofs**: zkWASM via `zkwasm-service-helper`
- **Web3**: `web3subscriber` from Delphinus Labs

## Project Structure

```
zk-2048/
├── src/
│   ├── app/                    # Redux store configuration
│   │   ├── hooks.ts            # Typed Redux hooks (useAppDispatch, useAppSelector)
│   │   └── store.ts            # Redux store with account, status, endpoint, dynamic slices
│   ├── components/             # Reusable UI components
│   │   ├── CommonBg.tsx        # Background wrapper component
│   │   ├── CommonButton.tsx    # Styled button component
│   │   ├── Currency.tsx        # Currency/score display
│   │   ├── History.tsx         # Game history display
│   │   ├── KeyControl.tsx      # Arrow key control UI
│   │   └── Nav.tsx             # Navigation bar with wallet connection
│   ├── data/                   # Redux slices and data models
│   │   ├── accountSlice.ts     # Wallet account state management
│   │   ├── abiAndAddress.ts    # Smart contract ABI and addresses
│   │   ├── application.ts      # Application type definitions
│   │   ├── base.ts             # Base types, HTTP client, ZK_MD5 config
│   │   ├── chainNet.ts         # Blockchain network configuration (Goerli)
│   │   ├── endpoint.ts         # zkWASM service endpoint management
│   │   ├── image.ts            # Image-related data
│   │   └── statusSlice.ts      # Proof task status management
│   ├── dynamic/                # Dynamic state slice
│   │   └── dynamicSlice.ts
│   ├── js/                     # WASM game logic
│   │   ├── g1024.c             # Game logic in C (2048 mechanics)
│   │   ├── g1024.wasm          # Compiled WebAssembly binary
│   │   ├── g1024.js            # WASM loader/wrapper
│   │   ├── g1024.d.ts          # TypeScript declarations for WASM
│   │   └── Makefile            # Build instructions for WASM
│   ├── layout/                 # Page layouts
│   │   ├── Main.tsx            # Main game layout and logic
│   │   ├── ConnectAccount.tsx  # Wallet connection component
│   │   └── layoutSlice.ts      # Layout state
│   ├── modals/                 # Modal dialogs
│   │   ├── addNewProveTask.tsx # ZK proof submission modal
│   │   ├── proofInfo.tsx       # Proof information display
│   │   └── base.tsx            # Base modal component
│   ├── sdk/                    # SDK utilities
│   │   └── task.ts             # Task types and interfaces for ZK proofs
│   ├── utils/                  # Utility functions
│   │   ├── address.ts          # Address formatting utilities
│   │   ├── inputs.tsx          # Input handling
│   │   ├── proof.ts            # Proof utilities
│   │   ├── shepherd.tsx        # Game tutorial (Shepherd.js)
│   │   └── string.ts           # String utilities
│   ├── images/                 # Game tile images (1.png - 17.png), icons
│   ├── fonts/                  # Custom fonts (Allerta, BeVietnamPro, Inter)
│   ├── abi/                    # Smart contract ABIs
│   ├── App.tsx                 # Root React component
│   ├── App.css                 # Global styles
│   └── index.tsx               # Application entry point
├── public/                     # Static assets
├── build/                      # Production build output
├── config-overrides.js         # react-app-rewired config (WASM support)
├── package.json                # Dependencies and scripts
├── tsconfig.json               # TypeScript configuration
└── .env                        # Environment variables
```

## Development Commands

```bash
# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build

# Run full dev workflow (build + start)
npm run dev

# Run linting/formatting (via lint-staged)
npm test

# Build WASM (requires clang-15 and zkWasm-C SDK)
cd src/js && make
```

## Git Hooks (Husky)

- **pre-commit**: Runs `npm test` (lint-staged: prettier + eslint)
- **pre-push**: Runs `npm run build` to ensure build passes

## Code Conventions

### TypeScript/React

- **Strict mode enabled** in TypeScript
- **Functional components** with React hooks
- **Redux Toolkit** for state management with typed hooks
- **Simple import sort** plugin for organized imports (auto-sorted)
- **Prettier** for formatting:
  - Single quotes
  - Trailing commas
  - No parens around single arrow function params

### File Naming

- React components: PascalCase (e.g., `CommonButton.tsx`)
- Redux slices: camelCase with `Slice` suffix (e.g., `accountSlice.ts`)
- Utilities: camelCase (e.g., `address.ts`)
- Styles: SCSS files named `style.scss` in component directories

### Imports Order (enforced by ESLint)

1. External libraries
2. Internal modules (relative paths)
3. Styles

### Redux State Structure

```typescript
{
  account: AccountState,   // Wallet connection state
  status: StatusState,     // ZK proof task status
  endpoint: EndpointState, // zkWASM service endpoints
  dynamic: DynamicState    // Dynamic/runtime state
}
```

## Key Components and Their Roles

### Game Logic (`src/js/g1024.c`)

The 2048 game logic is implemented in C and compiled to WASM:
- `step(direction)`: Move tiles (0=up, 1=left, 2=down, 3=right)
- `sell(n)`: Sell the highest tile at position n for currency
- `getBoard(index)`: Get tile value at index (0-15)
- `getCurrency()`: Get current score/currency
- `zkmain()`: Entry point for ZK proof generation

### Main Game Component (`src/layout/Main.tsx`)

- Manages game board state (4x4 grid = 16 cells)
- Handles keyboard input (Arrow keys and WASD)
- Tracks move commands for proof generation
- Integrates with WASM game instance

### Wallet Integration (`src/data/accountSlice.ts`)

- Uses `web3subscriber` for MetaMask/browser wallet connection
- Supports Goerli testnet by default
- Account state persisted in localStorage

### ZK Proof Submission (`src/modals/addNewProveTask.tsx`)

- Collects game commands as witness data
- Signs proof request with user's wallet
- Submits to zkWASM service via `zkwasm-service-helper`
- Links to ZKC Explorer for proof verification

## Environment Variables

Key variables in `.env`:
- `REACT_APP_ZKC_SERVER_URL`: ZKC RPC endpoint
- `MD5`: WASM image hash for proof verification
- `PROVING`: zkWASM proving service URL

## External Services

- **zkWASM Service**: `https://zkwasm-explorer.delphinuslab.com:8090`
- **ZKC RPC**: `https://rpc.zkcross.org/`
- **ZKC Explorer**: `https://scan.zkcross.org/`
- **ZKC Account**: `https://account.zkcross.org/`

## CI/CD

- **GitHub Actions** workflows in `.github/workflows/`
- **Vercel** deployment on push to main
- Pull request branches get preview deployments

## Common Tasks for AI Assistants

### Adding a New Component

1. Create component file in `src/components/` with PascalCase naming
2. Use functional component with TypeScript interface for props
3. Import styles from `style.scss` or create component-specific styles
4. Export component and add to relevant layout

### Modifying Game Logic

1. Edit `src/js/g1024.c`
2. Rebuild WASM: `cd src/js && make`
3. Update TypeScript declarations in `g1024.d.ts` if API changes
4. Test game functionality in browser

### Adding Redux State

1. Create slice in `src/data/` following existing patterns
2. Add reducer to `src/app/store.ts`
3. Create typed selectors and export actions
4. Use `useAppSelector` and `useAppDispatch` hooks in components

### Styling Guidelines

- Use Bootstrap classes where possible
- Custom styles in SCSS with BEM-like naming
- Gradient effects use `.gradient-content` class
- Responsive design with Bootstrap grid (Col, Row, Container)

## Important Notes

- The game board is a flat array of 16 integers (4x4 grid, row-major order)
- Tile values are stored as powers (1 = 2, 2 = 4, 3 = 8, etc.)
- Currency starts at 20 and decreases by 1 per move
- Selling a tile gives 2^(tile_value) currency
- Commands format: 0=up, 1=left, 2=down, 3=right, 4=sell (followed by cell index)
