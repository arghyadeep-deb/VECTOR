export const Z = {
  SCENE:          0,    // Three.js 3D scene
  BACKGROUND:     2,    // Grid + hex overlay
  DECORATIONS:    10,   // Rings, scanlines, vignette
  HOLOGRAM:       20,   // CentralHologram
  ARC_REACTOR:    25,   // ArcReactor
  LOWER_HUD:      35,   // Bar graph + EKG + mini radar
  EVENT_FEED:     40,   // Center event feed
  CORNER_HUD:     45,   // Compass + metric bars
  CORE_STATUS:    46,   // Draggable status panel
  SIDEBARS:       50,   // Telemetry + Districts panels
  OVERLAY:        50,   // VectorFrame brackets, reticle, status
  VOICE:          55,   // VoiceWaveform
  COMMAND_INPUT:  60,   // Command input area
  ALERTS:         80,   // AlertSystem toasts
  TICKER:         90,   // Ticker mode bar
  TOP_BAR:        100,  // TopBar + QuickActions
  METRICS:        101,  // SYSTEM METRICS panel
  FLOATING:       9999, // FloatingPanelManager portals
  ERROR:          99999,// ErrorBoundary fullscreen overlay
}
