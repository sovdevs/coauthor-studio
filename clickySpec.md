# spec.md

## Feature: Initial Typewriter Sound Integration

### Goal

Implement the first working version of typewriter sounds in the web interface using the two sound files currently available:

- `key1.wav`
- `return.wav`

Sound support should be optional, lightweight, and strictly frontend-driven.

This step is only about getting a minimal but working typewriter sound layer in place.

---

## 1. Available Sound Assets

Current sound directory:

```text
/Users/vmac/prog/PY/augmentedFiction/sounds
```

Current files:

- `key1.wav`
- `return.wav`

These two files are enough for a first implementation.

For now:

- `key1.wav` will be reused for normal keypresses
- `return.wav` will be used for both:
  - Enter (newline / carriage return)
  - Ctrl+Enter (submit)

Later, additional sounds may be added:

- `key2.wav`
- `key3.wav`
- `submit.wav`

But they are not required for this first step.

---

## 2. Scope of This Step

This step should implement:

- loading and using the two current sound files
- keypress sound playback in the web UI
- Enter sound playback
- Ctrl+Enter submit sound playback using the same `return.wav` for now
- a frontend sound toggle
- sound behavior that does not block typing

This step does **not** include:

- multiple key sound variants
- dedicated submit bell sound
- CLI sound support
- advanced audio mixing
- pitch randomization
- volume sliders
- per-key sound mapping
- typewriter sound support in export/manuscript generation

---

## 3. Sound Behavior Rules

### 3.1 Standard keypresses

When the user types normal printable characters, the frontend should play:

- `key1.wav`

This includes:
- letters
- numbers
- punctuation

Optional:
- also play on spacebar

Do **not** play sounds for:
- Shift
- Ctrl
- Alt
- Meta / Command
- arrow keys
- Escape
- function keys

### 3.2 Enter key

When the user presses `Enter` without Ctrl:

- insert a newline in the typing area
- play `return.wav`

### 3.3 Ctrl+Enter

When the user presses `Ctrl+Enter`:

- submit the current segment
- play `return.wav` for now

Later, this may be replaced by a dedicated `submit.wav`.

### 3.4 Backspace

For this first step:

- no sound required for Backspace

This can be added later if desired.

---

## 4. Frontend-Only Responsibility

Sound playback should be handled entirely in the frontend.

Do **not** route key sounds through:
- the backend
- the LLM
- any writing pipeline module

Sound playback is purely a UI behavior layer.

The writing engine should remain independent from audio.

---

## 5. File Placement

The two sound files should be placed somewhere the web app can serve statically.

Recommended target structure:

```text
public/sounds/typewriter/
  key1.wav
  return.wav
```

If the current project uses another static asset folder, adapt accordingly, but keep the directory clean and dedicated.

The original source directory is:

```text
/Users/vmac/prog/PY/augmentedFiction/sounds
```

---

## 6. Initial Audio Strategy

### 6.1 MVP approach

Use a very simple implementation first:

- preload the two sounds
- trigger them on appropriate keyboard events
- keep playback low-latency
- keep the logic easy to replace later

### 6.2 Acceptable implementation choices

For this first version, either approach is acceptable:

#### Option A: plain `Audio()` objects
Fastest to implement.

#### Option B: Web Audio API
Better long-term choice, but not required for this first step.

For MVP, plain audio playback is acceptable as long as it feels responsive enough.

---

## 7. Playback Rules

### 7.1 Avoid blocking typing

Sound playback must never:
- freeze the typing box
- delay input rendering
- interfere with Enter or Ctrl+Enter behavior

### 7.2 Allow repeated playback

Because the same `key1.wav` will be used repeatedly, the implementation must support rapid replay.

That means the frontend must not rely on a single long-running audio instance that cannot restart quickly.

A minimal acceptable solution is:

- create a short reusable playback strategy for repeated key taps

### 7.3 Volume

Set sound playback to a modest default volume.

The sound should feel atmospheric, not dominant.

If volume is configurable later, that is fine, but not required now.

---

## 8. Toggle Behavior

Add a simple sound toggle in the web UI.

### Requirements

- user can turn typewriter sounds on or off
- sound state should default to either:
  - off, for safety
  - or last remembered setting, if persistence already exists

### Minimum acceptable UI

One toggle control such as:

- `Typewriter sounds: On / Off`

This is enough for now.

No advanced sound settings are needed yet.

---

## 9. Event Mapping

Recommended mapping for this first implementation:

- printable character → `key1.wav`
- space → optional `key1.wav`
- Enter → `return.wav`
- Ctrl+Enter → `return.wav`

Do not trigger sounds for modifier-only presses.

---

## 10. Integration with Existing Input Model

This sound layer must work with the current multiline segment input model:

- Enter = newline
- Ctrl+Enter = submit

The sound logic should follow the actual input behavior, not override it.

That means:

- sound plays alongside the action
- sound never changes the meaning of the key

---

## 11. Suggested TODO List

### Asset preparation
- [ ] Copy `key1.wav` into the app's static/public sound folder
- [ ] Copy `return.wav` into the app's static/public sound folder
- [ ] Confirm both files load correctly from the browser

### Frontend audio layer
- [ ] Add a lightweight frontend sound utility
- [ ] Preload `key1.wav`
- [ ] Preload `return.wav`
- [ ] Expose simple functions such as:
  - [ ] `playKeySound()`
  - [ ] `playReturnSound()`

### Keyboard integration
- [ ] Detect printable character input in the typing box
- [ ] Play `key1.wav` for printable characters
- [ ] Detect Enter without Ctrl
- [ ] Play `return.wav` for Enter
- [ ] Detect Ctrl+Enter submit
- [ ] Play `return.wav` for Ctrl+Enter

### UI toggle
- [ ] Add a simple sound on/off toggle to the web UI
- [ ] Prevent playback when toggle is off

### Testing
- [ ] Test rapid typing
- [ ] Test Enter repeatedly
- [ ] Test Ctrl+Enter submission
- [ ] Confirm sounds do not block typing
- [ ] Confirm sounds do not fire for modifier-only keys

---

## 12. Non-Goals for This Step

Do not implement yet:

- additional key sound variants
- randomized key sound selection
- pitch variation
- separate submit sound
- carriage bell effect
- backspace sound
- CLI sound support
- user volume slider
- manuscript page sound behavior
- audio tied to text rendering

---

## 13. Expected Result

At the end of this step, the web UI should have:

- one working keypress sound
- one working return/submission sound
- support for multiline segment typing
- basic optional typewriter atmosphere
- no dependency on backend or LLM for sound playback

This is enough to validate the overall interaction before expanding the sound system later.

---

## 14. Next Likely Upgrade After This

Once the two-sound MVP works, the next upgrade can be:

- add `key2.wav` and `key3.wav`
- add a dedicated `submit.wav`
- randomize key sound selection
- move to Web Audio API if needed
- add optional subtle typewriter bell behavior
