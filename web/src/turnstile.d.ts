interface TurnstileRenderOptions {
  sitekey: string
  action: string
  callback: (token: string) => void
  'expired-callback'?: () => void
  'error-callback'?: (errorCode: string) => void
}

interface Window {
  turnstile?: {
    render: (container: HTMLElement, options: TurnstileRenderOptions) => string
    remove: (widgetId: string) => void
    reset: (widgetId: string) => void
  }
}
