import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { Logo } from "@/components/shared/Logo";

function FullScreenLoader() {
  return (
    <div className="grid min-h-screen place-items-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <Logo showWordmark={false} size={44} />
        <div className="h-1 w-32 overflow-hidden rounded-full bg-surface-muted">
          <div className="h-full w-1/2 animate-[shimmer_1.2s_infinite] rounded-full bg-primary" />
        </div>
      </div>
    </div>
  );
}

/** The page someone tried to open while signed out. It is honoured for ten minutes only: an old one must not send a later sign-in somewhere unexpected. */
const RETURN_FOR_MS = 10 * 60 * 1000;
function destination() {
  let path: string | null = null;
  try {
    const saved = JSON.parse(sessionStorage.getItem("synex.returnTo") ?? "null") as { path?: string; at?: number } | null;
    if (saved?.path && typeof saved.at === "number" && Date.now() - saved.at < RETURN_FOR_MS) path = saved.path;
  } catch { /* an old or damaged value is simply not used */ }
  return path && /^\/(?!\/)/.test(path) && !path.includes("\\") ? path : "/dashboard";
}
export function ProtectedRoute() {
  const {isAuthenticated,isLoading}=useAuth();const location=useLocation();
  const current=location.pathname+location.search;
  const target=destination();
  useEffect(()=>{
    if (isLoading) return;
    if (!isAuthenticated) sessionStorage.setItem("synex.returnTo", JSON.stringify({ path: current, at: Date.now() }));
    else if (current===target || location.pathname!=="/dashboard") sessionStorage.removeItem("synex.returnTo");
  },[current,target,isLoading,isAuthenticated,location.pathname]);
  if(isLoading)return <FullScreenLoader/>;
  if(!isAuthenticated)return <Navigate to="/login" state={{from:location}} replace/>;
  if(location.pathname==="/dashboard" && target!==current && target!=="/dashboard")return <Navigate to={target} replace/>;
  return <Outlet/>;
}
export function PublicOnlyRoute() {
  const {isAuthenticated,isLoading}=useAuth();
  if(isLoading)return <FullScreenLoader/>;
  if(isAuthenticated)return <Navigate to={destination()} replace/>;
  return <Outlet/>;
}
