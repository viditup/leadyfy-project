// ---------------------------------------------------------------------------
// Single entry point every page/component uses to read or write data.
// Talks directly to the real FastAPI backend — no mock layer. Every path
// below is copied from the backend's own OpenAPI schema (GET /openapi.json),
// not guessed, so it matches app/routers/*.py exactly.
//
// List endpoints return a paginated envelope on the wire:
//   { items: [...], total, page, per_page, total_pages }
// Since every existing page/table in this app (DataTable.jsx) already does
// its own client-side pagination over a plain array, the `list()` helper
// below unwraps `.items` and fetches a generous per_page so the full demo
// dataset comes back in one request. `listPage()` is available for the rare
// case a caller wants the raw envelope (total count, etc).
// ---------------------------------------------------------------------------
import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const http = axios.create({ baseURL: BASE_URL });

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('leadyfy_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Central 401 handling: bounce back to login if the token is invalid/expired.
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('leadyfy_token');
      localStorage.removeItem('leadyfy_user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export function getErrorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // FastAPI 422 validation errors: [{loc, msg, type}, ...]
    return detail.map((e) => e.msg).join(', ');
  }
  return error?.message || 'Something went wrong. Please try again.';
}

async function listPage(path, params = {}) {
  const res = await http.get(path, { params: { per_page: 200, ...params } });
  return res.data; // { items, total, page, per_page, total_pages }
}

async function list(path, params = {}) {
  const page = await listPage(path, params);
  return page.items;
}

async function get(path) {
  const res = await http.get(path);
  return res.data;
}
async function post(path, body) {
  const res = await http.post(path, body);
  return res.data;
}
async function put(path, body) {
  const res = await http.put(path, body);
  return res.data;
}
async function patch(path, body) {
  const res = await http.patch(path, body);
  return res.data;
}
async function del(path) {
  const res = await http.delete(path);
  return res.data;
}

export const api = {
  // ---- Auth ----
  login: (email, password) => post('/api/auth/login', { email, password }),
  me: () => get('/api/auth/me'),
  register: (payload) => post('/api/auth/register', payload),

  // ---- Clients ----
  getClients: (params) => list('/api/clients', params),
  getClientsPage: (params) => listPage('/api/clients', params),
  getClient: (id) => get(`/api/clients/${id}`),
  createClient: (payload) => post('/api/clients', payload),
  updateClient: (id, payload) => put(`/api/clients/${id}`, payload),
  deleteClient: (id) => del(`/api/clients/${id}`),
  getClientAssets: (id) => get(`/api/clients/${id}/assets`),
  addClientAsset: (id, payload) => post(`/api/clients/${id}/assets`, payload),
  invitePortalUser: (id, payload) => post(`/api/clients/${id}/portal-invite`, payload),

  // ---- Orders ----
  getOrders: (params) => list('/api/orders', params),
  getOrder: (id) => get(`/api/orders/${id}`),
  createOrder: (payload) => post('/api/orders', payload),
  updateOrder: (id, payload) => put(`/api/orders/${id}`, payload),
  deleteOrder: (id) => del(`/api/orders/${id}`),
  getOrderProductionCounter: (id) => get(`/api/orders/${id}/production-counter`),
  getMyPortalOrders: (params) => list('/api/orders/portal/mine', params),

  // ---- Scripts ----
  getScripts: (params) => list('/api/scripts', params),
  getScript: (id) => get(`/api/scripts/${id}`),
  createScript: (payload) => post('/api/scripts', payload),
  updateScript: (id, payload) => put(`/api/scripts/${id}`, payload),
  deleteScript: (id) => del(`/api/scripts/${id}`),
  clientReviewScript: (id, payload) => post(`/api/scripts/${id}/client-review`, payload),
  getMyPortalScripts: (params) => list('/api/scripts/portal/mine', params),

  // ---- Creators ----
  getCreators: (params) => list('/api/creators', params),
  getCreator: (id) => get(`/api/creators/${id}`),
  createCreator: (payload) => post('/api/creators', payload),
  updateCreator: (id, payload) => put(`/api/creators/${id}`, payload),
  deleteCreator: (id) => del(`/api/creators/${id}`),
  getCreatorAvailability: (id) => get(`/api/creators/${id}/availability`),
  addCreatorAvailability: (id, payload) => post(`/api/creators/${id}/availability`, payload),

  // ---- Shoots ----
  getShoots: (params) => list('/api/shoots', params),
  getShoot: (id) => get(`/api/shoots/${id}`),
  createShoot: (payload) => post('/api/shoots', payload),
  updateShoot: (id, payload) => put(`/api/shoots/${id}`, payload),
  deleteShoot: (id) => del(`/api/shoots/${id}`),
  updateShootChecklist: (id, payload) => patch(`/api/shoots/${id}/checklist`, payload),

  // ---- Videos ----
  getVideos: (params) => list('/api/videos', params),
  getVideo: (id) => get(`/api/videos/${id}`),
  createVideo: (payload) => post('/api/videos', payload),
  updateVideo: (id, payload) => put(`/api/videos/${id}`, payload),
  deleteVideo: (id) => del(`/api/videos/${id}`),
  transitionVideo: (id, status) => post(`/api/videos/${id}/transition`, { status }),
  getEditorDashboard: (params) => list('/api/videos/editor-dashboard', params),
  getMyPortalVideos: (params) => list('/api/videos/portal/mine', params),
  getVideoFeedback: (id) => get(`/api/videos/${id}/client-feedback`),
  submitVideoFeedback: (id, payload) => post(`/api/videos/${id}/client-feedback`, payload),
  getMyPortalVideoFeedback: (id) => get(`/api/videos/portal/${id}/client-feedback`),

  // ---- Tasks ----
  getTasks: (params) => list('/api/tasks', params),
  getTask: (id) => get(`/api/tasks/${id}`),
  createTask: (payload) => post('/api/tasks', payload),
  updateTask: (id, payload) => put(`/api/tasks/${id}`, payload),
  deleteTask: (id) => del(`/api/tasks/${id}`),

  // ---- Support Tickets ----
  getTickets: (params) => list('/api/support-tickets', params),
  getTicket: (id) => get(`/api/support-tickets/${id}`),
  updateTicket: (id, payload) => put(`/api/support-tickets/${id}`, payload),
  createPortalTicket: (payload) => post('/api/support-tickets/portal', payload),
  getMyPortalTickets: (params) => list('/api/support-tickets/portal/mine', params),
  getMyPortalTicket: (id) => get(`/api/support-tickets/portal/${id}`),

  // ---- Employees ----
  getEmployees: (params) => list('/api/employees', params),
  getEmployee: (id) => get(`/api/employees/${id}`),
  createEmployee: (payload) => post('/api/employees', payload),
  updateEmployee: (id, payload) => put(`/api/employees/${id}`, payload),

  // ---- Finance ----
  getPayments: (params) => list('/api/finance/payments', params),
  getPayment: (id) => get(`/api/finance/payments/${id}`),
  createPayment: (payload) => post('/api/finance/payments', payload),
  updatePayment: (id, payload) => put(`/api/finance/payments/${id}`, payload),
  getExpenses: (params) => list('/api/finance/expenses', params),
  createExpense: (payload) => post('/api/finance/expenses', payload),
  deleteExpense: (id) => del(`/api/finance/expenses/${id}`),
  getPayouts: (params) => list('/api/finance/creator-payouts', params),
  createPayout: (payload) => post('/api/finance/creator-payouts', payload),
  updatePayout: (id, payload) => put(`/api/finance/creator-payouts/${id}`, payload),
  getFinancialSummary: () => get('/api/finance/summary'),
  getMyPortalPayments: (params) => list('/api/finance/portal/mine', params),
  getMyPortalPayment: (id) => get(`/api/finance/portal/${id}`),

  // ---- Notifications ----
  getNotifications: (params) => list('/api/notifications', params),
  markNotificationRead: (id) => post(`/api/notifications/${id}/read`),
  markAllNotificationsRead: () => post('/api/notifications/read-all'),

  // ---- Dashboard ----
  getExecutiveDashboard: () => get('/api/dashboard/executive'),
  getMyWorkDashboard: () => get('/api/dashboard/my-work'),
  getPortalDashboard: () => get('/api/dashboard/portal'),
};

export default api;
