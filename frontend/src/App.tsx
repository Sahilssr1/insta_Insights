import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { useAuth } from './hooks/useAuth';
import { Skeleton } from './components/ui';
import { Audience } from './pages/Audience';
import { Connect, RequireAccount } from './pages/Connect';
import { Content } from './pages/Content';
import { Dashboard } from './pages/Dashboard';
import { MediaDetail } from './pages/MediaDetail';

function Unreachable() {
  return (
    <div style={{ padding: 48, maxWidth: 560, margin: '0 auto', textAlign: 'center' }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>📡</div>
      <h2 style={{ margin: '0 0 8px' }}>Can't reach the server</h2>
      <p style={{ color: 'var(--text-dim)' }}>
        InsightBoard's backend isn't responding right now. Please try again in a moment.
      </p>
    </div>
  );
}

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div style={{ padding: 40, maxWidth: 800, margin: '0 auto' }}>
        <Skeleton height={28} width="40%" />
        <div style={{ height: 16 }} />
        <Skeleton height={200} />
      </div>
    );
  }
  if (!user) return <Unreachable />;
  return <>{children}</>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/*"
          element={
            <Protected>
              <Layout>
                <Routes>
                  <Route path="/" element={<RequireAccount><Dashboard /></RequireAccount>} />
                  <Route path="/content" element={<RequireAccount><Content /></RequireAccount>} />
                  <Route path="/content/:id" element={<RequireAccount><MediaDetail /></RequireAccount>} />
                  <Route path="/audience" element={<RequireAccount><Audience /></RequireAccount>} />
                  <Route path="/connect" element={<Connect />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Layout>
            </Protected>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
