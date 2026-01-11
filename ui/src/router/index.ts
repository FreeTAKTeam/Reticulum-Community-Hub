import { createRouter } from "vue-router";
import { createWebHistory } from "vue-router";
import AboutPage from "../pages/AboutPage.vue";
import ConfigurePage from "../pages/ConfigurePage.vue";
import ConnectPage from "../pages/ConnectPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import FilesPage from "../pages/FilesPage.vue";
import TopicsPage from "../pages/TopicsPage.vue";
import UsersPage from "../pages/UsersPage.vue";
import WebMapPage from "../pages/WebMapPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardPage },
    { path: "/webmap", name: "webmap", component: WebMapPage },
    { path: "/topics", name: "topics", component: TopicsPage },
    { path: "/files", name: "files", component: FilesPage },
    { path: "/users", name: "users", component: UsersPage },
    { path: "/configure", name: "configure", component: ConfigurePage },
    { path: "/about", name: "about", component: AboutPage },
    { path: "/connect", name: "connect", component: ConnectPage }
  ]
});

export default router;
