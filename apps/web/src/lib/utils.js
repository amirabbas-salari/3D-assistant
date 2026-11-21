export function errorMessage(error) {
  return error instanceof Error ? error.message : String(error || 'خطای نامشخص');
}
export function messageTime() {
  return new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
