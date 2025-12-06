import { config } from '../aws-exports';

const STORAGE_KEY = 'consultant_auth_tokens';

export interface AuthTokens {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  expiresAt: number;
}

export interface ConsultantInfo {
  sub: string;
  email: string;
  email_verified: boolean;
  consultant_id?: string;
}

class AuthService {
  async login(): Promise<void> {
    if (config.demoMode) {
      const mockTokens: AuthTokens = {
        accessToken: 'demo-access-token',
        idToken: 'demo-id-token',
        refreshToken: 'demo-refresh-token',
        expiresAt: Date.now() + 3600000,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(mockTokens));
      return;
    }

    const loginUrl = this.getCognitoLoginUrl();
    globalThis.location.href = loginUrl;
  }

  async handleCallback(): Promise<void> {
    if (config.demoMode) return;

    const urlParams = new URLSearchParams(globalThis.location.search);
    const code = urlParams.get('code');
    const error = urlParams.get('error');
    const errorDescription = urlParams.get('error_description');

    if (error) {
      console.error('OAuth Error:', error, errorDescription);
      throw new Error(`Authentication failed: ${errorDescription || error}`);
    }

    if (!code) return;

    try {
      const tokens = await this.exchangeCodeForTokens(code);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
      globalThis.location.href = '/';
    } catch (err) {
      console.error('Token exchange failed:', err);
      throw err;
    }
  }

  async isAuthenticated(): Promise<boolean> {
    if (config.demoMode) {
      return localStorage.getItem(STORAGE_KEY) !== null;
    }

    const tokens = this.getTokens();
    if (!tokens) return false;

    if (tokens.expiresAt <= Date.now()) {
      try {
        await this.refreshAccessToken();
        return true;
      } catch {
        this.clearTokens();
        return false;
      }
    }

    return true;
  }

  async getConsultantInfo(): Promise<ConsultantInfo | null> {
    if (config.demoMode) {
      return {
        sub: 'demo-user',
        email: 'consultant@demo.com',
        email_verified: true,
        consultant_id: '1'
      };
    }

    const tokens = this.getTokens();
    if (!tokens) return null;

    try {
      const cognitoDomain = config.cognitoDomain.startsWith('https://') 
        ? config.cognitoDomain 
        : `https://${config.cognitoDomain}`;
      
      const response = await fetch(`${cognitoDomain}/oauth2/userInfo`, {
        headers: {
          'Authorization': `Bearer ${tokens.accessToken}`
        }
      });

      if (!response.ok) throw new Error('Failed to get user info');

      const data = await response.json();
      return {
        sub: data.sub,
        email: data.email,
        email_verified: data.email_verified,
        consultant_id: data['custom:consultant_id']
      };
    } catch (error) {
      console.error('Error getting user info:', error);
      return null;
    }
  }

  async logout(): Promise<void> {
    this.clearTokens();

    if (!config.demoMode && config.cognitoDomain && config.cognitoClientId) {
      const cognitoDomain = config.cognitoDomain.startsWith('https://') 
        ? config.cognitoDomain 
        : `https://${config.cognitoDomain}`;
      const logoutUrl = `${cognitoDomain}/logout?` +
        `client_id=${config.cognitoClientId}&` +
        `logout_uri=${encodeURIComponent(config.cloudFrontUrl || globalThis.location.origin)}`;
      globalThis.location.href = logoutUrl;
    } else {
      globalThis.location.href = '/';
    }
  }

  getTokens(): AuthTokens | null {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    try {
      return JSON.parse(stored);
    } catch {
      return null;
    }
  }

  getAccessToken(): string | null {
    const tokens = this.getTokens();
    return tokens?.accessToken || null;
  }

  getIdToken(): string | null {
    const tokens = this.getTokens();
    return tokens?.idToken || null;
  }

  private clearTokens(): void {
    localStorage.removeItem(STORAGE_KEY);
  }

  private getCognitoLoginUrl(): string {
    const redirectUri = config.cloudFrontUrl
      ? `${config.cloudFrontUrl}/callback`
      : `${globalThis.location.origin}/callback`;

    const cognitoDomain = config.cognitoDomain.startsWith('https://') 
      ? config.cognitoDomain 
      : `https://${config.cognitoDomain}`;

    return `${cognitoDomain}/oauth2/authorize?` +
      `client_id=${config.cognitoClientId}&` +
      `response_type=code&` +
      `scope=openid+email+profile&` +
      `redirect_uri=${encodeURIComponent(redirectUri)}`;
  }

  private async exchangeCodeForTokens(code: string): Promise<AuthTokens> {
    const redirectUri = config.cloudFrontUrl
      ? `${config.cloudFrontUrl}/callback`
      : `${globalThis.location.origin}/callback`;

    const cognitoDomain = config.cognitoDomain.startsWith('https://') 
      ? config.cognitoDomain 
      : `https://${config.cognitoDomain}`;

    const response = await fetch(`${cognitoDomain}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: config.cognitoClientId,
        code: code,
        redirect_uri: redirectUri,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Token exchange failed: ${errorText}`);
    }

    const data = await response.json();
    return {
      accessToken: data.access_token,
      idToken: data.id_token,
      refreshToken: data.refresh_token,
      expiresAt: Date.now() + (data.expires_in * 1000),
    };
  }

  private async refreshAccessToken(): Promise<void> {
    const tokens = this.getTokens();
    if (!tokens?.refreshToken) throw new Error('No refresh token');

    const response = await fetch(`${config.cognitoDomain}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        client_id: config.cognitoClientId,
        refresh_token: tokens.refreshToken,
      }),
    });

    if (!response.ok) throw new Error('Token refresh failed');

    const data = await response.json();
    const newTokens: AuthTokens = {
      accessToken: data.access_token,
      idToken: data.id_token,
      refreshToken: tokens.refreshToken,
      expiresAt: Date.now() + (data.expires_in * 1000),
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(newTokens));
  }
}

export const authService = new AuthService();
