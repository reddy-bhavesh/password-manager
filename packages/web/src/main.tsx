import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import { App } from "./App";
import { AuthLayout } from "./routes/AuthLayout";
import { HomeRoute } from "./routes/HomeRoute";
import { LoginPage } from "./routes/LoginPage";
import { MfaPage } from "./routes/MfaPage";
import { VaultPage } from "./routes/VaultPage";
import "./styles.css";

const queryClient = new QueryClient();

const rootRoute = createRootRoute({
  component: () => <App />
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomeRoute
});

const authRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  component: AuthLayout
});

const loginRoute = createRoute({
  getParentRoute: () => authRoute,
  path: "/login",
  component: LoginPage
});

const mfaRoute = createRoute({
  getParentRoute: () => authRoute,
  path: "/mfa",
  component: MfaPage
});

const vaultRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/vault",
  component: VaultPage
});

const routeTree = rootRoute.addChildren([indexRoute, authRoute.addChildren([loginRoute, mfaRoute]), vaultRoute]);

const router = createRouter({
  routeTree
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
);
