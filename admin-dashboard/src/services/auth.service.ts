import { config } from '../aws-exports';

const STORAGE_KEY = 'auth_tokens';

export interface AuthTokens {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  expiresAt: number;
}

export interface UserInfo {
  sub: string;
  email: string;
  email_verified: boolean;
  name?: string;
}

class AuthService {
  // Demo mode - bypass Cognito
  async login(): Promise<void> {
    if (config.demoMode) {
      // Mock login for demo
      const mockTokens: AuthTokens = {
        accessToken: 'demo-access-token',
        idToken: 'demo-id-token',
        refreshToken: 'demo-refresh-token',
        expiresAt: Date.now() + 3600000, // 1 hour
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(mockTokens));
      return;
    }

    // Real Cognito login
    const loginUrl = this.getCognitoLoginUrl();
    window.location.href = loginUrl;
  }

  async handleCallback(): Promise<void> {
    if (config.demoMode) {
      return;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');

    if (!code) {
      throw new Error('No authorization code found');
    }

    // Exchange code for tokens
    const tokens = await this.exchangeCodeForTokens(code);
    this.storeTokens(tokens);

    // Redirect to home
    window.history.replaceState({}, document.title, '/');
  }

  async logout(): Promise<void> {
    localStorage.removeItem(STORAGE_KEY);
    
    if (config.demoMode) {
      window.location.href = '/';
      return;
    }

    const logoutUrl = `https://${config.cognitoDomain}/logout?client_id=${config.cognitoClientId}&logout_uri=${encodeURIComponent(window.location.origin)}`;
    window.location.href = logoutUrl;
  }

  isAuthenticated(): boolean {
    const tokens = this.getTokens();
    if (!tokens) return false;

    // Check if token expired
    return tokens.expiresAt > Date.now();
  }

  getCurrentUser(): UserInfo | null {
    if (config.demoMode) {
      return {
        sub: 'demo-user-123',
        email: 'demo@example.com',
        email_verified: true,
        name: 'Demo User',
      };
    }

    const tokens = this.getTokens();
    if (!tokens) return null;

    try {
      const payload = JSON.parse(atob(tokens.idToken.split('.')[1]));
      return {
        sub: payload.sub,
        email: payload.email,
        email_verified: payload.email_verified,
        name: payload.name,
      };
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

  private getTokens(): AuthTokens | null {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;

    try {
      return JSON.parse(stored);
    } catch {
      return null;
    }
  }

  private storeTokens(tokens: AuthTokens): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  }

  private getCognitoLoginUrl(): string {
    const params = new URLSearchParams({
      client_id: config.cognitoClientId,
      response_type: 'code',
      scope: 'openid email profile',
      redirect_uri: `${window.location.origin}/callback`,
    });

    return `https://${config.cognitoDomain}/oauth2/authorize?${params.toString()}`;
  }

  private async exchangeCodeForTokens(code: string): Promise<AuthTokens> {
    const response = await fetch(`https://${config.cognitoDomain}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: config.cognitoClientId,
        code,
        redirect_uri: `${window.location.origin}/callback`,
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to exchange code for tokens');
    }

    const data = await response.json();
    return {
      accessToken: data.access_token,
      idToken: data.id_token,
      refreshToken: data.refresh_token,
      expiresAt: Date.now() + data.expires_in * 1000,
    };
  }
}

export const authService = new AuthService();