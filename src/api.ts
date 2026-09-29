export type Config = { apiUrl: string; clientId: string; region: string };
export type Session = { token: string; expires: number };
export type Job = { id: string; status: 'queued'|'running'|'complete'|'failed'; engine: string; error?: string; seconds?: number; pages?: number; bytes?: number; url?: string };
export async function signIn(config: Config, username: string, password: string): Promise<Session> {
  const response = await fetch(`https://cognito-idp.${config.region}.amazonaws.com/`, {
    method: 'POST', headers: { 'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth' },
    body: JSON.stringify({ AuthFlow: 'USER_PASSWORD_AUTH', ClientId: config.clientId, AuthParameters: { USERNAME: username, PASSWORD: password } })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || 'Sign-in failed.');
  if (!data.AuthenticationResult) throw new Error('Your account requires a password change. Contact the app administrator.');
  return { token: data.AuthenticationResult.IdToken, expires: Date.now() + data.AuthenticationResult.ExpiresIn * 1000 };
}
export async function request<T>(config: Config, session: Session, path: string, body?: unknown): Promise<T> {
  if (Date.now() >= session.expires) throw new Error('Your session expired. Sign out and sign in again.');
  const response = await fetch(config.apiUrl + path, { method: body ? 'POST' : 'GET', headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.message || 'The request failed. Please retry.');
  return data;
}
export async function uploadFile(config: Config, session: Session, file: File) {
  const { id, upload } = await request<{id: string; upload: {url: string; fields: Record<string,string>}}>(config, session, '/uploads', { size: file.size });
  const form = new FormData();
  Object.entries(upload.fields).forEach(([key,value]) => form.append(key,value));
  form.append('file', file);
  const response = await fetch(upload.url, { method: 'POST', body: form });
  if (!response.ok) throw new Error('Upload failed. Check your connection and retry.');
  return id;
}
