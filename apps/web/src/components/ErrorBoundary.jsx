import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    // در کنسول مرورگر لاگ می‌شود و با addLog هم می‌توان نمایش داد
    console.error('[ErrorBoundary]', error, info);
  }
  render() {
    if (this.state.hasError) {
      const msg = this.state.error?.message || String(this.state.error || 'خطای نامشخص');
      const fallback = this.props.fallback;
      if (fallback) return typeof fallback === 'function' ? fallback(this.state.error) : fallback;
      return (
        <div style={{ padding: 14, border: '1px solid #e6c1c1', borderRadius: 8, background: '#fff5f5', color: '#7a2e2e', fontSize: 11, lineHeight: 1.8 }}>
          <strong>⚠️ خطا در رندر این بخش</strong>
          <div style={{ marginTop: 6, fontFamily: 'ui-monospace,monospace', fontSize: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: '#fff', border: '1px solid #f0d0d0', borderRadius: 6, padding: '8px 10px' }}>{msg}</div>
          <button onClick={() => this.setState({ hasError: false, error: null })} style={{ marginTop: 10 }} className="secondary-button compact">تلاش دوباره</button>
        </div>
      );
    }
    return this.props.children;
  }
}
