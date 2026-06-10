// Decode a JWT payload without verifying the signature.
// Verification happens on the backend — this is just for reading claims.
export function decodeJWT<T>(token: string): T {
  const base64 = token.split('.')[1]
    .replace(/-/g, '+')
    .replace(/_/g, '/')
  return JSON.parse(atob(base64)) as T
}
