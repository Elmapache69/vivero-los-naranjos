'use strict';

// ══════════════════════════════════════════════════════════════════
//  ESTADO GLOBAL
// ══════════════════════════════════════════════════════════════════
const API = '/api';

const state = {
  usuario:      null,   // { id, nombre, username, rol, totp_enabled }
  accessToken:  null,
  refreshToken: null,
  productos:    [],
  categorias:   [],
  fichas:       [],
  clientes:     [],
  proveedores:  [],
  permisos:     { perm_cajero_descuento: true, perm_cajero_clientes: false },
  carro:        [],
  itemsCompra:  [],
  refreshTimer: null,
};

// ══════════════════════════════════════════════════════════════════
//  HTTP CLIENT — todas las peticiones pasan por aquí
// ══════════════════════════════════════════════════════════════════
async function api(method, path, body = null, retry = true) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.accessToken) headers['Authorization'] = `Bearer ${state.accessToken}`;

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API}${path}`, opts);

  // Token expirado — intentar refresh automático una sola vez
  if (res.status === 401 && retry && state.refreshToken) {
    const ok = await tryRefreshToken();
    if (ok) return api(method, path, body, false);
    doLogout();
    return null;
  }

  if (res.status === 204) return true;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
    throw new Error(err.detail || `Error ${res.status}`);
  }
  return res.json();
}

const get    = (path)        => api('GET',    path);
const post   = (path, body)  => api('POST',   path, body);
const put    = (path, body)  => api('PUT',    path, body);
const patch  = (path, body)  => api('PATCH',  path, body);
const del    = (path)        => api('DELETE', path);

// ══════════════════════════════════════════════════════════════════
//  TOKENS — almacenamiento y refresco automático
// ══════════════════════════════════════════════════════════════════
function saveTokens(access, refresh) {
  state.accessToken  = access;
  state.refreshToken = refresh;
  // Guardar refresh token en sessionStorage (no localStorage por seguridad)
  sessionStorage.setItem('rt', refresh);
  scheduleTokenRefresh();
}

function loadStoredTokens() {
  const rt = sessionStorage.getItem('rt');
  if (rt) state.refreshToken = rt;
}

async function tryRefreshToken() {
  if (!state.refreshToken) return false;
  try {
    const res = await fetch(`${API}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    state.accessToken = data.access_token;
    scheduleTokenRefresh();
    return true;
  } catch {
    return false;
  }
}

function scheduleTokenRefresh() {
  // Refrescar token cada 7 horas (access token dura 8h)
  clearTimeout(state.refreshTimer);
  state.refreshTimer = setTimeout(tryRefreshToken, 7 * 60 * 60 * 1000);
}

// ══════════════════════════════════════════════════════════════════
//  SIDEBAR RESPONSIVE
// ══════════════════════════════════════════════════════════════════
function toggleSidebar() {
  ['sidebar','hamburger','sidebar-overlay'].forEach(id => document.getElementById(id).classList.toggle('open'));
}
function closeSidebar() {
  ['sidebar','hamburger','sidebar-overlay'].forEach(id => document.getElementById(id).classList.remove('open'));
}

// ══════════════════════════════════════════════════════════════════
//  AUTH — LOGIN, 2FA, LOGOUT
// ══════════════════════════════════════════════════════════════════
async function doLogin() {
  const username = document.getElementById('login-user').value.trim();
  const password = document.getElementById('login-pass').value;
  if (!username || !password) { showLoginError('Ingresa usuario y contraseña'); return; }

  setLoginLoading(true);
  try {
    const data = await post('/auth/login', { username, password });
    if (!data) return;

    if (data.requires_2fa) {
      // Mostrar panel 2FA
      document.getElementById('panel-login').style.display = 'none';
      document.getElementById('panel-2fa').style.display = 'block';
      document.querySelector('#totp-inputs input').focus();
      return;
    }
    await onLoginSuccess(data);
  } catch (e) {
    showLoginError(e.message);
  } finally {
    setLoginLoading(false);
  }
}

// 2FA — navegación entre inputs de código
function totpNext(input, idx) {
  input.value = input.value.replace(/\D/g, '');
  const inputs = document.querySelectorAll('#totp-inputs input');
  if (input.value && idx < 5) inputs[idx + 1].focus();
  if (input.value && idx === 5) submit2FA();
}

async function submit2FA() {
  const inputs = document.querySelectorAll('#totp-inputs input');
  const code = Array.from(inputs).map(i => i.value).join('');
  if (code.length < 6) { document.getElementById('totp-error').style.display = 'block'; document.getElementById('totp-error').textContent = 'Ingresa el código completo de 6 dígitos'; return; }

  setLoginLoading(true);
  try {
    const username = document.getElementById('login-user').value.trim();
    const password = document.getElementById('login-pass').value;
    const data = await post('/auth/login', { username, password, totp_code: code });
    if (!data) return;
    document.getElementById('totp-error').style.display = 'none';
    await onLoginSuccess(data);
  } catch (e) {
    document.getElementById('totp-error').style.display = 'block';
    document.getElementById('totp-error').textContent = e.message;
    // Limpiar inputs
    document.querySelectorAll('#totp-inputs input').forEach(i => i.value = '');
    document.querySelector('#totp-inputs input').focus();
  } finally {
    setLoginLoading(false);
  }
}

function resetLogin() {
  document.getElementById('panel-login').style.display = 'block';
  document.getElementById('panel-2fa').style.display = 'none';
  document.querySelectorAll('#totp-inputs input').forEach(i => i.value = '');
}

async function onLoginSuccess(data) {
  saveTokens(data.access_token, data.refresh_token);
  state.usuario = data.user;

  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'block';
  document.getElementById('user-nombre').textContent = state.usuario.nombre;
  document.getElementById('user-rol').textContent = { admin: 'Administrador', cajero: 'Cajero', bodeguero: 'Bodeguero' }[state.usuario.rol] || state.usuario.rol;
  document.getElementById('fecha-hoy').textContent = new Date().toLocaleDateString('es-CL', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  if (state.usuario.totp_enabled) {
    document.getElementById('badge-2fa').style.display = 'inline-block';
  }

  await cargarDatos();
  await cargarConfiguracion();
  aplicarMenuSegunRol();
}

function aplicarMenuSegunRol() {
  const rol = state.usuario.rol;
  if (rol === 'cajero') {
    document.getElementById('admin-menu').style.display = 'none';
    showPage('pos');
  } else if (rol === 'bodeguero') {
    document.getElementById('admin-menu').style.display = 'block';
    // Ocultar secciones no permitidas para bodeguero
    document.querySelectorAll('.nav-item').forEach(n => {
      const oc = n.getAttribute('onclick') || '';
      const permitidos = ["'productos'", "'fichas'", "'mermas'", "'seguridad'"];
      const visible = permitidos.some(p => oc.includes(p));
      n.style.display = visible ? '' : 'none';
    });
    showPage('productos');
  } else {
    document.getElementById('admin-menu').style.display = 'block';
    showPage('dashboard');
  }
}

function doLogout() {
  clearTimeout(state.refreshTimer);
  sessionStorage.removeItem('rt');
  Object.assign(state, { usuario: null, accessToken: null, refreshToken: null, carro: [], productos: [], clientes: [] });
  document.getElementById('app').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
  resetLogin();
  document.getElementById('login-pass').value = '';
  document.getElementById('badge-2fa').style.display = 'none';
  document.querySelectorAll('.nav-item').forEach(n => n.style.display = '');
}

function showLoginError(msg) {
  const el = document.getElementById('login-error');
  el.textContent = msg; el.style.display = 'block';
}

function setLoginLoading(loading) {
  const btn = document.getElementById('btn-login');
  const btn2 = document.getElementById('btn-2fa');
  [btn, btn2].forEach(b => { if (b) b.disabled = loading; });
}

// ══════════════════════════════════════════════════════════════════
//  CARGAR DATOS GLOBALES
// ══════════════════════════════════════════════════════════════════
async function cargarDatos() {
  const [productos, categorias, fichas, clientes, proveedores] = await Promise.all([
    get('/productos').catch(() => []),
    get('/categorias').catch(() => []),
    get('/fichas').catch(() => []),
    get('/clientes').catch(() => []),
    get('/proveedores').catch(() => []),
  ]);
  Object.assign(state, { productos, categorias, fichas, clientes, proveedores });
}

async function cargarConfiguracion() {
  try {
    const cfgs = await get('/configuracion');
    if (Array.isArray(cfgs)) {
      state.permisos = {};
      cfgs.forEach(c => { state.permisos[c.clave] = c.valor; });
    }
  } catch { /* no fatal */ }
}

// ══════════════════════════════════════════════════════════════════
//  NAVEGACIÓN
// ══════════════════════════════════════════════════════════════════
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pg = document.getElementById(`page-${name}`);
  if (pg) pg.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if ((n.getAttribute('onclick') || '').includes(`'${name}'`)) n.classList.add('active');
  });
  closeSidebar();

  const loaders = {
    dashboard: cargarDashboard, pos: renderPOS,
    productos: cargarProductos, fichas: cargarFichas,
    clientes: cargarClientes, proveedores: cargarProveedores,
    compras: cargarCompras, ventas: cargarVentas,
    mermas: cargarMermas, reportes: cargarReporte,
    cierre: cargarCierre, usuarios: cargarUsuarios,
    seguridad: cargarSeguridad, auditoria: cargarAuditoria,
  };
  loaders[name]?.();
}

// ══════════════════════════════════════════════════════════════════
//  DASHBOARD
// ══════════════════════════════════════════════════════════════════
async function cargarDashboard() {
  try {
    const d = await get('/reportes/dashboard');
    document.getElementById('dash-metrics').innerHTML = `
      <div class="metric-card verde"><div class="metric-label">Ventas hoy</div><div class="metric-icon">💵</div><div class="metric-value">${fmt(d.ventas_hoy)}</div></div>
      <div class="metric-card"><div class="metric-label">Ventas del mes</div><div class="metric-icon">📅</div><div class="metric-value">${fmt(d.ventas_mes)}</div></div>
      <div class="metric-card info"><div class="metric-label">N° ventas hoy</div><div class="metric-icon">🧾</div><div class="metric-value">${d.num_ventas_hoy}</div></div>
      <div class="metric-card"><div class="metric-label">Productos</div><div class="metric-icon">🌿</div><div class="metric-value">${d.productos_activos}</div></div>
      <div class="metric-card danger"><div class="metric-label">Alertas stock</div><div class="metric-icon">⚠️</div><div class="metric-value">${d.alertas_stock}</div></div>
      <div class="metric-card"><div class="metric-label">Clientes</div><div class="metric-icon">👥</div><div class="metric-value">${d.total_clientes}</div></div>
    `;
    const maxG = Math.max(...d.grafico_semana.map(g => g.total), 1);
    document.getElementById('dash-grafico').innerHTML = d.grafico_semana.length
      ? `<div class="chart-bar">${d.grafico_semana.map(g => `
          <div class="chart-bar-item">
            <span class="chart-bar-label">${g.dia.slice(5)}</span>
            <div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct(g.total, maxG)}%"></div></div>
            <span class="chart-bar-val">${fmt(g.total)}</span>
          </div>`).join('')}</div>`
      : emptyChart('Sin ventas esta semana');

    const maxC = Math.max(...d.ventas_por_categoria.map(c => c.total), 1);
    document.getElementById('dash-categorias').innerHTML = d.ventas_por_categoria.length
      ? `<div class="chart-bar">${d.ventas_por_categoria.map(c => `
          <div class="chart-bar-item">
            <span class="chart-bar-label">${c.nombre}</span>
            <div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct(c.total, maxC)}%;background:var(--naranja-claro)"></div></div>
            <span class="chart-bar-val">${fmt(c.total)}</span>
          </div>`).join('')}</div>`
      : emptyChart('Sin ventas este mes');

    // Alertas de stock
    const alertas = state.productos.filter(p => p.stock <= p.stock_minimo && p.is_active);
    document.getElementById('dash-alertas').innerHTML = alertas.length
      ? `<div class="table-wrap"><table>
          <thead><tr><th>Producto</th><th>Stock</th><th>Mínimo</th><th>Estado</th></tr></thead>
          <tbody>${alertas.map(a => `<tr>
            <td>${a.nombre}</td>
            <td class="${a.stock === 0 ? 'stock-critical' : 'stock-low'}">${a.stock} ${a.unidad}</td>
            <td>${a.stock_minimo}</td>
            <td><span class="badge ${a.stock === 0 ? 'badge-danger' : 'badge-naranja'}">${a.stock === 0 ? 'Sin stock' : 'Stock bajo'}</span></td>
          </tr>`).join('')}</tbody></table></div>`
      : '<div class="alert alert-success">✅ Todos los productos tienen stock suficiente.</div>';
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  POS
// ══════════════════════════════════════════════════════════════════
function renderPOS() {
  const cats = document.getElementById('pos-categoria');
  cats.innerHTML = '<option value="">Todas las categorías</option>' +
    state.categorias.map(c => `<option value="${c.id}">${c.nombre}</option>`).join('');
  const selCli = document.getElementById('pos-cliente');
  if (selCli) {
    selCli.innerHTML = '<option value="">Sin cliente</option>' +
      state.clientes.map(c => `<option value="${c.id}">${c.nombre}${c.tipo !== 'regular' ? ' ⭐' : ''}</option>`).join('');
  }
  // Permisos cajero
  if (state.usuario.rol === 'cajero') {
    const showDesc = state.permisos['perm_cajero_descuento'] === 'true';
    const showCli  = state.permisos['perm_cajero_clientes']  === 'true';
    document.getElementById('row-descuento').style.display = showDesc ? 'flex' : 'none';
    document.getElementById('row-cliente-pos').style.display = showCli ? 'block' : 'none';
  }
  filtrarPOS();
}

function filtrarPOS() {
  const q   = (document.getElementById('pos-search')?.value || '').toLowerCase();
  const cat = document.getElementById('pos-categoria')?.value;
  const filtrados = state.productos.filter(p =>
    p.is_active &&
    p.stock > 0 &&
    (!q   || p.nombre.toLowerCase().includes(q) || (p.codigo || '').toLowerCase().includes(q)) &&
    (!cat || String(p.categoria_id) === cat)
  );
  document.getElementById('pos-productos').innerHTML = filtrados.length
    ? filtrados.map(p => `
        <div class="pos-producto-btn" onclick="agregarAlCarro(${p.id})">
          <div class="pname">${p.nombre}</div>
          <div class="pprice">${fmt(p.precio_venta)}</div>
          <div class="pstock">Stock: ${p.stock} ${p.unidad}</div>
        </div>`).join('')
    : `<p style="color:var(--gris);grid-column:1/-1;padding:1rem;font-size:.9rem">No hay productos disponibles</p>`;
}

async function buscarPorCodigo() {
  const codigo = document.getElementById('pos-codigo').value.trim();
  if (!codigo) return;
  try {
    const prod = await get(`/productos/codigo/${encodeURIComponent(codigo)}`);
    if (prod) { agregarAlCarro(prod.id, prod); document.getElementById('pos-codigo').value = ''; toast(`✅ ${prod.nombre} agregado`); }
  } catch { toast('Producto no encontrado', 'error'); }
}

function agregarAlCarro(pid, prodData = null) {
  const prod = prodData || state.productos.find(p => p.id === pid);
  if (!prod) return;
  const existe = state.carro.find(i => i.id === pid);
  if (existe) {
    if (existe.qty >= prod.stock) { toast('Sin stock suficiente', 'error'); return; }
    existe.qty++;
  } else {
    state.carro.push({ id: pid, nombre: prod.nombre, precio: prod.precio_venta, qty: 1, stock: prod.stock });
  }
  renderCarro();
}

function cambiarQty(pid, delta) {
  const item = state.carro.find(i => i.id === pid);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) state.carro = state.carro.filter(i => i.id !== pid);
  renderCarro();
}

function limpiarCarro() {
  state.carro = [];
  document.getElementById('carro-descuento').value = 0;
  document.getElementById('efectivo-recibido').value = 0;
  document.getElementById('cambio-box').style.display = 'none';
  renderCarro();
}

function renderCarro() {
  const cont = document.getElementById('carro-items');
  if (!state.carro.length) {
    cont.innerHTML = '<div class="carro-empty">Selecciona un producto<br>para empezar</div>';
    actualizarTotal(); return;
  }
  cont.innerHTML = state.carro.map(item => `
    <div class="carro-item">
      <div class="carro-item-name">${item.nombre}</div>
      <div class="carro-qty">
        <button onclick="cambiarQty(${item.id},-1)">−</button>
        <span>${item.qty}</span>
        <button onclick="cambiarQty(${item.id},1)">+</button>
      </div>
      <div class="carro-precio">${fmt(item.precio * item.qty)}</div>
      <button class="carro-remove" onclick="state.carro=state.carro.filter(i=>i.id!==${item.id});renderCarro()">✕</button>
    </div>`).join('');
  actualizarTotal();
}

function actualizarTotal() {
  const sub  = state.carro.reduce((s, i) => s + i.precio * i.qty, 0);
  const desc = parseFloat(document.getElementById('carro-descuento')?.value) || 0;
  document.getElementById('carro-subtotal').textContent = fmt(sub);
  document.getElementById('carro-total').textContent = fmt(Math.max(0, sub - desc));
  calcularCambio();
}

function toggleEfectivo() {
  const esEfectivo = document.getElementById('metodo-pago').value === 'efectivo';
  document.getElementById('row-efectivo').style.display = esEfectivo ? 'block' : 'none';
  if (!esEfectivo) document.getElementById('cambio-box').style.display = 'none';
}

function calcularCambio() {
  const sub   = state.carro.reduce((s, i) => s + i.precio * i.qty, 0);
  const desc  = parseFloat(document.getElementById('carro-descuento')?.value) || 0;
  const total = Math.max(0, sub - desc);
  const ef    = parseFloat(document.getElementById('efectivo-recibido')?.value) || 0;
  const box   = document.getElementById('cambio-box');
  if (document.getElementById('metodo-pago').value === 'efectivo' && ef > 0) {
    const cambio = ef - total;
    box.style.display = 'block';
    box.style.background = cambio >= 0 ? 'var(--verde-fondo)' : '#fff5f5';
    document.getElementById('cambio-valor').textContent = cambio >= 0 ? fmt(cambio) : '⚠️ Monto insuficiente';
    document.getElementById('cambio-valor').style.color = cambio >= 0 ? 'var(--verde)' : 'var(--danger)';
  } else {
    box.style.display = 'none';
  }
}

async function procesarVenta() {
  if (!state.carro.length) { toast('El carrito está vacío', 'error'); return; }
  const sub   = state.carro.reduce((s, i) => s + i.precio * i.qty, 0);
  const desc  = parseFloat(document.getElementById('carro-descuento').value) || 0;
  const total = Math.max(0, sub - desc);
  const metodo = document.getElementById('metodo-pago').value;
  const ef = parseFloat(document.getElementById('efectivo-recibido').value) || 0;
  if (metodo === 'efectivo' && ef > 0 && ef < total) { toast('Efectivo insuficiente para el total', 'error'); return; }

  try {
    const body = {
      metodo_pago: metodo,
      descuento: desc,
      efectivo_recibido: ef,
      cliente_id: parseInt(document.getElementById('pos-cliente')?.value) || null,
      items: state.carro.map(i => ({ producto_id: i.id, cantidad: i.qty, precio_unitario: i.precio })),
    };
    const v = await post('/ventas', body);
    let msg = `✅ ${v.numero_boleta} — Total: ${fmt(v.total)}`;
    if (v.vuelto > 0) msg += ` | Vuelto: ${fmt(v.vuelto)}`;
    toast(msg);
    limpiarCarro();
    await cargarDatos();
    filtrarPOS();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  PRODUCTOS
// ══════════════════════════════════════════════════════════════════
async function cargarProductos() {
  state.productos = await get('/productos').catch(() => []);
  document.getElementById('tabla-productos').innerHTML = state.productos.map(p => {
    const sc = p.stock_estado === 'sin_stock' ? 'stock-critical' : p.stock_estado === 'bajo' ? 'stock-low' : 'stock-ok';
    return `<tr>
      <td><code style="font-size:.78rem;background:var(--fondo);padding:.1rem .4rem;border-radius:4px">${p.codigo || '—'}</code></td>
      <td><strong>${p.nombre}</strong>${p.ficha_nombre ? `<br><small style="color:var(--gris);font-style:italic">${p.ficha_nombre}</small>` : ''}</td>
      <td>${p.categoria_nombre || '—'}</td>
      <td><span class="${sc}">${p.stock} ${p.unidad}</span></td>
      <td>${fmt(p.precio_venta)}</td>
      <td>${p.precio_costo > 0 ? fmt(p.precio_costo) : '—'}</td>
      <td>${p.margen_porcentaje > 0 ? `<span class="badge badge-verde">${p.margen_porcentaje}%</span>` : '—'}</td>
      <td style="display:flex;gap:.4rem;flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" onclick="editarProducto(${p.id})">Editar</button>
        <button class="btn btn-danger btn-sm" onclick="eliminarProducto(${p.id})">Eliminar</button>
      </td>
    </tr>`;
  }).join('') || `<tr><td colspan="8" class="table-empty">No hay productos registrados</td></tr>`;
}

function abrirModalProducto() {
  v('prod-id').value = '';
  ['prod-nombre','prod-codigo','prod-pventa','prod-pcosto','prod-stock'].forEach(id => v(id).value = '');
  v('prod-stockmin').value = 5;
  v('prod-categoria').innerHTML = '<option value="">Sin categoría</option>' + state.categorias.map(c => `<option value="${c.id}">${c.nombre}</option>`).join('');
  v('prod-ficha').innerHTML = '<option value="">Sin ficha</option>' + state.fichas.map(f => `<option value="${f.id}">${f.nombre_comun}</option>`).join('');
  v('modal-prod-title').textContent = 'Nuevo Producto';
  abrirModal('modal-producto');
}

function editarProducto(id) {
  const p = state.productos.find(x => x.id === id); if (!p) return;
  abrirModalProducto();
  v('prod-id').value = p.id;
  v('prod-nombre').value = p.nombre;
  v('prod-codigo').value = p.codigo || '';
  v('prod-pventa').value = p.precio_venta;
  v('prod-pcosto').value = p.precio_costo;
  v('prod-stock').value = p.stock;
  v('prod-stockmin').value = p.stock_minimo;
  v('prod-categoria').value = p.categoria_id || '';
  v('prod-ficha').value = p.ficha_planta_id || '';
  v('prod-unidad').value = p.unidad;
  v('modal-prod-title').textContent = 'Editar Producto';
}

async function guardarProducto() {
  const id = v('prod-id').value;
  const body = {
    nombre: v('prod-nombre').value,
    codigo: v('prod-codigo').value || null,
    categoria_id: parseInt(v('prod-categoria').value) || null,
    ficha_planta_id: parseInt(v('prod-ficha').value) || null,
    precio_venta: parseFloat(v('prod-pventa').value) || 0,
    precio_costo: parseFloat(v('prod-pcosto').value) || 0,
    stock: parseInt(v('prod-stock').value) || 0,
    stock_minimo: parseInt(v('prod-stockmin').value) || 5,
    unidad: v('prod-unidad').value,
  };
  if (!body.nombre || !body.precio_venta) { toast('Nombre y precio son obligatorios', 'error'); return; }
  try {
    await (id ? put(`/productos/${id}`, body) : post('/productos', body));
    toast('Producto guardado ✅'); cerrarModal('modal-producto');
    await cargarDatos(); cargarProductos();
  } catch (e) { toast(e.message, 'error'); }
}

async function eliminarProducto(id) {
  if (!confirm('¿Eliminar este producto?')) return;
  try {
    await del(`/productos/${id}`);
    toast('Producto eliminado'); await cargarDatos(); cargarProductos();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  FICHAS
// ══════════════════════════════════════════════════════════════════
async function cargarFichas() {
  state.fichas = await get('/fichas').catch(() => []);
  document.getElementById('fichas-grid').innerHTML = state.fichas.length
    ? state.fichas.map(f => `
        <div class="ficha-card">
          <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:.5rem">
            <div>
              <div class="ficha-nombre">🪴 ${f.nombre_comun}</div>
              ${f.nombre_cientifico ? `<div class="ficha-cientifico">${f.nombre_cientifico}</div>` : ''}
            </div>
            <button class="btn btn-secondary btn-sm" onclick="editarFicha(${f.id})">Editar</button>
          </div>
          ${f.descripcion ? `<p style="font-size:.83rem;color:var(--gris);margin-bottom:.7rem;line-height:1.5">${f.descripcion.slice(0, 100)}${f.descripcion.length > 100 ? '…' : ''}</p>` : ''}
          <div class="ficha-tags">
            ${f.riego ? `<span class="ficha-tag">💧 ${f.riego}</span>` : ''}
            ${f.luz ? `<span class="ficha-tag">☀️ ${f.luz}</span>` : ''}
            ${f.sustrato ? `<span class="ficha-tag">🪨 ${f.sustrato.slice(0, 20)}</span>` : ''}
            ${f.temporada_venta ? `<span class="ficha-tag">🗓️ ${f.temporada_venta}</span>` : ''}
            ${f.temporada_floracion ? `<span class="ficha-tag">🌸 ${f.temporada_floracion}</span>` : ''}
            ${f.temperatura_min != null ? `<span class="ficha-tag">🌡️ ${f.temperatura_min}°–${f.temperatura_max}°C</span>` : ''}
          </div>
          ${f.notas_ia ? `<div style="margin-top:.7rem;padding:.5rem .7rem;background:var(--verde-fondo);border-radius:8px;font-size:.78rem;color:var(--verde)">🤖 ${f.notas_ia.slice(0, 120)}${f.notas_ia.length > 120 ? '…' : ''}</div>` : ''}
        </div>`).join('')
    : '<p style="color:var(--gris)">No hay fichas registradas.</p>';
}

function abrirModalFicha() {
  v('ficha-id').value = '';
  ['ficha-comun','ficha-cientifico','ficha-descripcion','ficha-sustrato','ficha-tmin','ficha-tmax','ficha-tfloracion','ficha-ia'].forEach(id => v(id).value = '');
  ['ficha-riego','ficha-luz','ficha-tventa'].forEach(id => v(id).value = '');
  v('modal-ficha-title').textContent = 'Nueva Ficha';
  abrirModal('modal-ficha');
}

function editarFicha(id) {
  const f = state.fichas.find(x => x.id === id); if (!f) return;
  abrirModalFicha();
  v('ficha-id').value = f.id;
  v('ficha-comun').value = f.nombre_comun || '';
  v('ficha-cientifico').value = f.nombre_cientifico || '';
  v('ficha-descripcion').value = f.descripcion || '';
  v('ficha-riego').value = f.riego || '';
  v('ficha-luz').value = f.luz || '';
  v('ficha-sustrato').value = f.sustrato || '';
  v('ficha-tmin').value = f.temperatura_min || '';
  v('ficha-tmax').value = f.temperatura_max || '';
  v('ficha-tventa').value = f.temporada_venta || '';
  v('ficha-tfloracion').value = f.temporada_floracion || '';
  v('ficha-ia').value = f.notas_ia || '';
  v('modal-ficha-title').textContent = 'Editar Ficha';
}

async function guardarFicha() {
  const id = v('ficha-id').value;
  const body = {
    nombre_comun: v('ficha-comun').value,
    nombre_cientifico: v('ficha-cientifico').value || null,
    descripcion: v('ficha-descripcion').value || null,
    riego: v('ficha-riego').value || null,
    luz: v('ficha-luz').value || null,
    sustrato: v('ficha-sustrato').value || null,
    temperatura_min: parseFloat(v('ficha-tmin').value) || null,
    temperatura_max: parseFloat(v('ficha-tmax').value) || null,
    temporada_venta: v('ficha-tventa').value || null,
    temporada_floracion: v('ficha-tfloracion').value || null,
    notas_ia: v('ficha-ia').value || null,
  };
  if (!body.nombre_comun) { toast('El nombre común es obligatorio', 'error'); return; }
  try {
    await (id ? put(`/fichas/${id}`, body) : post('/fichas', body));
    toast('Ficha guardada ✅'); cerrarModal('modal-ficha'); await cargarDatos(); cargarFichas();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  CLIENTES
// ══════════════════════════════════════════════════════════════════
async function cargarClientes() {
  state.clientes = await get('/clientes').catch(() => []);
  const tl = { regular: 'Regular', frecuente: 'Frecuente ⭐', mayorista: 'Mayorista 🏢' };
  document.getElementById('tabla-clientes').innerHTML = state.clientes.map(c => `
    <tr>
      <td><strong>${c.nombre}</strong></td><td>${c.rut || '—'}</td>
      <td>${c.telefono || '—'}</td><td>${c.email || '—'}</td>
      <td><span class="badge ${c.tipo === 'frecuente' ? 'badge-naranja' : c.tipo === 'mayorista' ? 'badge-info' : 'badge-gris'}">${tl[c.tipo]}</span></td>
      <td>${c.saldo_favor > 0 ? `<span class="badge badge-verde">${fmt(c.saldo_favor)}</span>` : '—'}</td>
      <td><button class="btn btn-secondary btn-sm" onclick="editarCliente(${c.id})">Editar</button></td>
    </tr>`).join('') || `<tr><td colspan="7" class="table-empty">No hay clientes</td></tr>`;
}

function abrirModalCliente() {
  v('cli-id').value = ''; ['cli-nombre','cli-rut','cli-telefono','cli-email','cli-direccion'].forEach(id => v(id).value = ''); v('cli-tipo').value = 'regular';
  v('modal-cli-title').textContent = 'Nuevo Cliente'; abrirModal('modal-cliente');
}

function editarCliente(id) {
  const c = state.clientes.find(x => x.id === id); if (!c) return;
  abrirModalCliente(); v('cli-id').value = c.id; v('cli-nombre').value = c.nombre;
  v('cli-rut').value = c.rut || ''; v('cli-telefono').value = c.telefono || '';
  v('cli-email').value = c.email || ''; v('cli-direccion').value = c.direccion || '';
  v('cli-tipo').value = c.tipo; v('modal-cli-title').textContent = 'Editar Cliente';
}

async function guardarCliente() {
  const id = v('cli-id').value;
  const body = { nombre: v('cli-nombre').value, rut: v('cli-rut').value || null, telefono: v('cli-telefono').value || null, email: v('cli-email').value || null, direccion: v('cli-direccion').value || null, tipo: v('cli-tipo').value };
  if (!body.nombre) { toast('El nombre es obligatorio', 'error'); return; }
  try { await (id ? put(`/clientes/${id}`, body) : post('/clientes', body)); toast('Cliente guardado ✅'); cerrarModal('modal-cliente'); await cargarDatos(); cargarClientes(); }
  catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  PROVEEDORES
// ══════════════════════════════════════════════════════════════════
async function cargarProveedores() {
  state.proveedores = await get('/proveedores').catch(() => []);
  document.getElementById('tabla-proveedores').innerHTML = state.proveedores.map(p => `
    <tr><td><strong>${p.nombre}</strong></td><td>${p.rut || '—'}</td><td>${p.contacto || '—'}</td>
    <td>${p.telefono || '—'}</td><td>${p.email || '—'}</td>
    <td><button class="btn btn-secondary btn-sm" onclick="editarProveedor(${p.id})">Editar</button></td></tr>`)
    .join('') || `<tr><td colspan="6" class="table-empty">No hay proveedores</td></tr>`;
}

function abrirModalProveedor() { ['prov-id','prov-nombre','prov-rut','prov-contacto','prov-telefono','prov-email','prov-direccion'].forEach(id => v(id).value = ''); abrirModal('modal-proveedor'); }
function editarProveedor(id) { const p = state.proveedores.find(x => x.id === id); if (!p) return; abrirModalProveedor(); v('prov-id').value = p.id; v('prov-nombre').value = p.nombre; v('prov-rut').value = p.rut || ''; v('prov-contacto').value = p.contacto || ''; v('prov-telefono').value = p.telefono || ''; v('prov-email').value = p.email || ''; v('prov-direccion').value = p.direccion || ''; }
async function guardarProveedor() { const id = v('prov-id').value; const body = { nombre: v('prov-nombre').value, rut: v('prov-rut').value || null, contacto: v('prov-contacto').value || null, telefono: v('prov-telefono').value || null, email: v('prov-email').value || null, direccion: v('prov-direccion').value || null }; if (!body.nombre) { toast('El nombre es obligatorio', 'error'); return; } try { await (id ? put(`/proveedores/${id}`, body) : post('/proveedores', body)); toast('Proveedor guardado ✅'); cerrarModal('modal-proveedor'); await cargarDatos(); cargarProveedores(); } catch (e) { toast(e.message, 'error'); } }

// ══════════════════════════════════════════════════════════════════
//  COMPRAS
// ══════════════════════════════════════════════════════════════════
async function cargarCompras() {
  const compras = await get('/compras').catch(() => []);
  document.getElementById('tabla-compras').innerHTML = compras.map(c => `
    <tr><td><code style="font-size:.8rem">${c.numero_orden}</code></td><td>${c.proveedor_nombre || '—'}</td>
    <td><strong>${fmt(c.total)}</strong></td>
    <td><span class="badge ${c.estado === 'recibida' ? 'badge-verde' : c.estado === 'cancelada' ? 'badge-danger' : 'badge-naranja'}">${c.estado}</span></td>
    <td>${c.created_at?.slice(0, 10)}</td></tr>`).join('') || `<tr><td colspan="5" class="table-empty">Sin compras</td></tr>`;
}

function abrirModalCompra() { state.itemsCompra = [{ producto_id: '', cantidad: 1, precio: 0 }]; v('compra-proveedor').innerHTML = state.proveedores.map(p => `<option value="${p.id}">${p.nombre}</option>`).join(''); v('compra-notas').value = ''; renderItemsCompra(); abrirModal('modal-compra'); }
function agregarItemCompra() { state.itemsCompra.push({ producto_id: '', cantidad: 1, precio: 0 }); renderItemsCompra(); }
function renderItemsCompra() { document.getElementById('compra-items').innerHTML = state.itemsCompra.map((item, i) => `<div style="display:grid;grid-template-columns:1fr 80px 110px auto;gap:.5rem;margin-bottom:.5rem;align-items:center"><select onchange="state.itemsCompra[${i}].producto_id=this.value" style="padding:.5rem;border:1.5px solid var(--borde);border-radius:8px;outline:none;background:#fff"><option value="">Seleccionar...</option>${state.productos.map(p => `<option value="${p.id}" ${item.producto_id == p.id ? 'selected' : ''}>${p.nombre}</option>`).join('')}</select><input type="number" min="1" value="${item.cantidad}" onchange="state.itemsCompra[${i}].cantidad=parseInt(this.value)||1" style="padding:.5rem;border:1.5px solid var(--borde);border-radius:8px;text-align:center;outline:none"><input type="number" min="0" value="${item.precio}" placeholder="$ costo" onchange="state.itemsCompra[${i}].precio=parseFloat(this.value)||0" style="padding:.5rem;border:1.5px solid var(--borde);border-radius:8px;outline:none"><button onclick="state.itemsCompra.splice(${i},1);renderItemsCompra()" class="btn btn-danger btn-sm">✕</button></div>`).join(''); }
async function guardarCompra() { const items = state.itemsCompra.filter(i => i.producto_id && i.cantidad > 0); if (!items.length) { toast('Agrega al menos un producto', 'error'); return; } try { const v_ = await post('/compras', { proveedor_id: parseInt(v('compra-proveedor').value), notas: v('compra-notas').value || null, items: items.map(i => ({ producto_id: parseInt(i.producto_id), cantidad: i.cantidad, precio_unitario: i.precio })) }); toast(`Compra ${v_.numero_orden} registrada ✅`); cerrarModal('modal-compra'); await cargarDatos(); cargarCompras(); } catch (e) { toast(e.message, 'error'); } }

// ══════════════════════════════════════════════════════════════════
//  VENTAS
// ══════════════════════════════════════════════════════════════════
async function cargarVentas() {
  const ventas = await get('/ventas').catch(() => []);
  document.getElementById('tabla-ventas').innerHTML = ventas.map(vt => `
    <tr>
      <td><code style="font-size:.8rem">${vt.numero_boleta}</code></td>
      <td>${vt.cliente_nombre || '—'}</td><td>${vt.cajero_nombre || '—'}</td>
      <td><strong>${fmt(vt.total)}</strong></td>
      <td><span class="badge badge-gris">${vt.metodo_pago}</span></td>
      <td><span class="badge ${vt.estado === 'completada' ? 'badge-verde' : 'badge-danger'}">${vt.estado}</span></td>
      <td>${vt.created_at?.slice(0, 10)}</td>
      <td style="display:flex;gap:.3rem">
        <button class="btn btn-secondary btn-sm" onclick="verVenta(${vt.id},'${vt.numero_boleta}')">Ver</button>
        ${state.usuario.rol === 'admin' && vt.estado === 'completada' ? `<button class="btn btn-danger btn-sm" onclick="anularVenta(${vt.id})">Anular</button>` : ''}
      </td>
    </tr>`).join('') || `<tr><td colspan="8" class="table-empty">Sin ventas</td></tr>`;
}

async function verVenta(id, boleta) {
  const vt = await get(`/ventas/${id}`);
  document.getElementById('dv-title').textContent = `Detalle — ${boleta}`;
  document.getElementById('dv-body').innerHTML = `
    <div class="table-wrap"><table>
      <thead><tr><th>Producto</th><th>Cantidad</th><th>Precio unit.</th><th>Subtotal</th></tr></thead>
      <tbody>${vt.items.map(i => `<tr><td>${i.producto_nombre}</td><td>${i.cantidad}</td><td>${fmt(i.precio_unitario)}</td><td>${fmt(i.subtotal)}</td></tr>`).join('')}</tbody>
    </table></div>
    <div style="margin-top:1rem;border-top:1px solid var(--borde);padding-top:1rem">
      <div style="display:flex;justify-content:space-between;margin-bottom:.3rem"><span style="color:var(--gris)">Subtotal</span><span>${fmt(vt.subtotal)}</span></div>
      ${vt.descuento > 0 ? `<div style="display:flex;justify-content:space-between;margin-bottom:.3rem"><span style="color:var(--gris)">Descuento</span><span style="color:var(--danger)">−${fmt(vt.descuento)}</span></div>` : ''}
      <div style="display:flex;justify-content:space-between;font-size:1.1rem;font-weight:600;color:var(--verde)"><span>TOTAL</span><span>${fmt(vt.total)}</span></div>
      ${vt.vuelto > 0 ? `<div style="display:flex;justify-content:space-between;margin-top:.3rem"><span style="color:var(--gris)">Vuelto entregado</span><span>${fmt(vt.vuelto)}</span></div>` : ''}
    </div>`;
  abrirModal('modal-detalle-venta');
}

async function anularVenta(id) {
  const motivo = prompt('Motivo de anulación (mínimo 5 caracteres):');
  if (!motivo || motivo.length < 5) return;
  try { await post(`/ventas/${id}/anular`, { motivo }); toast('Venta anulada'); cargarVentas(); } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  MERMAS
// ══════════════════════════════════════════════════════════════════
async function cargarMermas() {
  const mermas = await get('/mermas').catch(() => []);
  document.getElementById('tabla-mermas').innerHTML = mermas.map(m => `
    <tr><td>${m.producto_nombre}</td><td><span class="badge badge-danger">−${m.cantidad}</span></td>
    <td>${m.costo_total > 0 ? `<span style="color:var(--danger)">${fmt(m.costo_total)}</span>` : '—'}</td>
    <td>${m.motivo}</td><td>${m.usuario_nombre || '—'}</td><td>${m.created_at?.slice(0, 10)}</td></tr>`)
    .join('') || `<tr><td colspan="6" class="table-empty">Sin mermas registradas</td></tr>`;
}

function abrirModalMerma() { v('merma-producto').innerHTML = state.productos.map(p => `<option value="${p.id}">${p.nombre} (stock: ${p.stock})</option>`).join(''); v('merma-cantidad').value = 1; abrirModal('modal-merma'); }
async function guardarMerma() { const body = { producto_id: parseInt(v('merma-producto').value), cantidad: parseInt(v('merma-cantidad').value), motivo: v('merma-motivo').value }; try { await post('/mermas', body); toast('Merma registrada'); cerrarModal('modal-merma'); await cargarDatos(); cargarMermas(); } catch (e) { toast(e.message, 'error'); } }

// ══════════════════════════════════════════════════════════════════
//  REPORTES
// ══════════════════════════════════════════════════════════════════
async function cargarReporte() {
  try {
    const per = v('reporte-periodo').value;
    const d = await get(`/reportes/ventas?periodo=${per}`);
    document.getElementById('rep-metrics').innerHTML = `
      <div class="metric-card verde"><div class="metric-label">Total ventas</div><div class="metric-value">${fmt(d.total_ventas)}</div></div>
      <div class="metric-card"><div class="metric-label">N° ventas</div><div class="metric-value">${d.num_ventas}</div></div>
      <div class="metric-card naranja"><div class="metric-label">Ticket promedio</div><div class="metric-value">${fmt(d.ticket_promedio)}</div></div>
    `;
    const maxD = Math.max(...d.ventas_por_dia.map(x => x.total), 1);
    document.getElementById('rep-dias').innerHTML = d.ventas_por_dia.length
      ? `<div class="chart-bar">${d.ventas_por_dia.map(x => `<div class="chart-bar-item"><span class="chart-bar-label">${x.dia.slice(5)}</span><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct(x.total,maxD)}%"></div></div><span class="chart-bar-val">${fmt(x.total)}</span></div>`).join('')}</div>`
      : emptyChart('Sin datos');
    const iconPago = { efectivo: '💵', debito: '💳', credito: '💳', transferencia: '📱' };
    const totalP = d.ventas_por_metodo.reduce((s, p) => s + p.total, 0) || 1;
    document.getElementById('rep-pagos').innerHTML = d.ventas_por_metodo.length
      ? `<div class="chart-bar">${d.ventas_por_metodo.map(p => `<div class="chart-bar-item"><span class="chart-bar-label">${iconPago[p.metodo] || ''} ${p.metodo}</span><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct(p.total,totalP)}%;background:var(--info)"></div></div><span class="chart-bar-val">${p.cantidad} vtas</span></div>`).join('')}</div>`
      : emptyChart('Sin datos');
    const maxV = Math.max(...d.top_productos.map(p => p.vendidos), 1);
    document.getElementById('rep-tops').innerHTML = d.top_productos.length
      ? `<div class="chart-bar">${d.top_productos.map(p => `<div class="chart-bar-item"><span class="chart-bar-label">${p.nombre}</span><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct(p.vendidos,maxV)}%"></div></div><span class="chart-bar-val">${p.vendidos} und.</span></div>`).join('')}</div>`
      : emptyChart('Sin ventas en este período');
    const maxM = Math.max(...d.margen_productos.map(p => p.margen), 1);
    document.getElementById('rep-margen').innerHTML = d.margen_productos.length
      ? `<div class="chart-bar">${d.margen_productos.map(p => `<div class="chart-bar-item"><span class="chart-bar-label">${p.nombre}</span><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct(Math.max(0,p.margen),maxM)}%;background:var(--naranja-claro)"></div></div><span class="chart-bar-val">${fmt(p.margen)}</span></div>`).join('')}</div>`
      : emptyChart('Sin datos de margen');
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  CIERRE DE CAJA
// ══════════════════════════════════════════════════════════════════
async function cargarCierre() {
  try {
    const [dash, historial] = await Promise.all([get('/reportes/dashboard'), get('/cierres-caja')]);
    const rep = await get('/reportes/ventas?periodo=dia');
    const efPago = rep.ventas_por_metodo.find(p => p.metodo === 'efectivo');
    document.getElementById('cierre-resumen').innerHTML = `
      <div class="cierre-stat verde"><label>Ventas del día</label><div class="val">${fmt(dash.ventas_hoy)}</div></div>
      <div class="cierre-stat"><label>N° de ventas</label><div class="val">${rep.num_ventas}</div></div>
      <div class="cierre-stat naranja"><label>Efectivo esperado</label><div class="val">${fmt(efPago?.total || 0)}</div></div>
      <div class="cierre-stat"><label>Ticket promedio</label><div class="val">${fmt(rep.ticket_promedio)}</div></div>
    `;
    document.getElementById('tabla-cierres').innerHTML = historial.map(c => `
      <tr><td>${c.created_at?.slice(0, 10)}</td><td>${c.usuario_nombre || '—'}</td>
      <td>${fmt(c.efectivo_contado)}</td>
      <td><span class="${Math.abs(c.diferencia) < 100 ? 'stock-ok' : c.diferencia < 0 ? 'stock-critical' : 'stock-low'}">${c.diferencia >= 0 ? '+' : ''}${fmt(c.diferencia)}</span></td></tr>`)
      .join('') || `<tr><td colspan="4" class="table-empty">Sin cierres</td></tr>`;
  } catch (e) { toast(e.message, 'error'); }
}

function calcularDiferencia() { const ef = parseFloat(v('cierre-efectivo').value) || 0; const preview = document.getElementById('cierre-preview'); preview.style.display = 'block'; preview.innerHTML = `Efectivo ingresado: <strong>${fmt(ef)}</strong>`; preview.style.background = 'var(--verde-fondo)'; }

async function realizarCierre() {
  const ef = parseFloat(v('cierre-efectivo').value) || 0;
  if (!confirm(`¿Confirmar cierre con ${fmt(ef)} en efectivo?`)) return;
  try {
    const r = await post('/cierres-caja', { efectivo_contado: ef, observaciones: v('cierre-obs').value || null });
    const preview = document.getElementById('cierre-preview');
    preview.style.display = 'block';
    preview.style.background = Math.abs(r.diferencia) < 500 ? 'var(--verde-fondo)' : '#fff5f5';
    preview.innerHTML = `✅ <strong>Cierre registrado</strong><br>Ventas: ${fmt(r.total_ventas)} (${r.num_ventas} ventas)<br>Efectivo sistema: ${fmt(r.efectivo_sistema)}<br>Efectivo contado: ${fmt(ef)}<br><strong style="color:${Math.abs(r.diferencia)<100?'var(--verde)':r.diferencia<0?'var(--danger)':'var(--naranja)'}">Diferencia: ${r.diferencia >= 0 ? '+' : ''}${fmt(r.diferencia)}</strong>`;
    v('cierre-efectivo').value = 0; v('cierre-obs').value = '';
    toast(`Cierre registrado — diferencia: ${fmt(r.diferencia)}`, Math.abs(r.diferencia) < 500 ? 'success' : 'warning');
    cargarCierre();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  USUARIOS
// ══════════════════════════════════════════════════════════════════
async function cargarUsuarios() {
  const usuarios = await get('/usuarios').catch(() => []);
  const rl = { admin: '👑 Admin', cajero: '🧾 Cajero', bodeguero: '📦 Bodeguero' };
  const rb = { admin: 'badge-naranja', cajero: 'badge-verde', bodeguero: 'badge-info' };
  document.getElementById('tabla-usuarios').innerHTML = usuarios.map(u => `
    <tr>
      <td><strong>${u.nombre}</strong></td>
      <td><code style="font-size:.85rem;background:var(--fondo);padding:.1rem .5rem;border-radius:4px">@${u.username}</code></td>
      <td><span class="badge ${rb[u.rol] || 'badge-gris'}">${rl[u.rol] || u.rol}</span></td>
      <td>${u.totp_enabled ? '<span class="badge badge-verde">✓ Activo</span>' : '<span class="badge badge-gris">No</span>'}</td>
      <td><span class="badge ${u.is_active ? 'badge-verde' : 'badge-gris'}">${u.is_active ? 'Activo' : 'Inactivo'}</span></td>
      <td>${u.last_login ? u.last_login.slice(0, 16).replace('T', ' ') : '—'}</td>
      <td style="display:flex;gap:.4rem;flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" onclick="toggleUsuario(${u.id},'${u.is_active}')">${u.is_active ? 'Desactivar' : 'Activar'}</button>
        ${u.rol !== 'admin' ? `<button class="btn btn-danger btn-sm" onclick="eliminarUsuario(${u.id})">Eliminar</button>` : ''}
      </td>
    </tr>`).join('') || `<tr><td colspan="7" class="table-empty">Sin usuarios</td></tr>`;
  // Cargar toggles de permisos
  await cargarConfiguracion();
  v('toggle-descuento').checked = state.permisos['perm_cajero_descuento'] === 'true';
  v('toggle-clientes').checked  = state.permisos['perm_cajero_clientes']  === 'true';
}

function abrirModalUsuario() { ['usr-nombre','usr-username','usr-password'].forEach(id => v(id).value = ''); v('usr-rol').value = 'cajero'; actualizarDescripcionRol(); abrirModal('modal-usuario'); }
function actualizarDescripcionRol() { const desc = { cajero: `🧾 <strong>Cajero</strong> — Acceso al Punto de Venta.${state.permisos['perm_cajero_descuento']==='true'?' Puede aplicar descuentos.':' Sin descuentos.'}`, bodeguero: `📦 <strong>Bodeguero</strong> — Inventario, fichas y mermas. Sin acceso a ventas ni finanzas.`, admin: `👑 <strong>Administrador</strong> — Acceso completo a todos los módulos.` }; document.getElementById('desc-rol').innerHTML = desc[v('usr-rol').value] || ''; }
async function guardarUsuario() { const body = { nombre: v('usr-nombre').value, username: v('usr-username').value, password: v('usr-password').value, rol: v('usr-rol').value }; if (!body.nombre || !body.username || !body.password) { toast('Todos los campos son obligatorios', 'error'); return; } try { await post('/usuarios', body); toast(`Usuario @${body.username} creado ✅`); cerrarModal('modal-usuario'); cargarUsuarios(); } catch (e) { toast(e.message, 'error'); } }
async function toggleUsuario(id) { try { await patch(`/usuarios/${id}`, {}); cargarUsuarios(); } catch (e) { toast(e.message, 'error'); } }
async function eliminarUsuario(id) { if (!confirm('¿Eliminar este usuario?')) return; try { await del(`/usuarios/${id}`); toast('Usuario desactivado'); cargarUsuarios(); } catch (e) { toast(e.message, 'error'); } }
async function guardarPermiso(clave, valor) { try { await put(`/configuracion/${clave}`, { valor: String(valor) }); state.permisos[clave] = String(valor); toast(`Permiso actualizado ✅`); } catch (e) { toast(e.message, 'error'); } }

// ══════════════════════════════════════════════════════════════════
//  SEGURIDAD — MI CUENTA
// ══════════════════════════════════════════════════════════════════
async function cargarSeguridad() {
  // Estado 2FA
  const box = document.getElementById('2fa-status-box');
  if (state.usuario.totp_enabled) {
    box.innerHTML = `
      <div class="alert alert-success">✅ El 2FA está activo en tu cuenta.</div>
      <button class="btn btn-danger" onclick="desactivar2FA()">Desactivar 2FA</button>`;
  } else {
    box.innerHTML = `
      <div class="alert alert-warning">⚠️ Tu cuenta no tiene 2FA activado. Se recomienda activarlo.</div>
      <button class="btn btn-primary" onclick="iniciarSetup2FA()">Activar 2FA</button>`;
  }
}

async function cambiarPassword() {
  const body = { current_password: v('pwd-actual').value, new_password: v('pwd-nueva').value, confirm_password: v('pwd-confirmar').value };
  if (!body.current_password || !body.new_password) { toast('Completa todos los campos', 'error'); return; }
  try {
    await post('/auth/change-password', body);
    toast('Contraseña actualizada ✅');
    ['pwd-actual','pwd-nueva','pwd-confirmar'].forEach(id => v(id).value = '');
  } catch (e) { toast(e.message, 'error'); }
}

async function iniciarSetup2FA() {
  try {
    const data = await post('/auth/2fa/setup', {});
    const box = document.getElementById('2fa-status-box');
    box.innerHTML = `
      <div class="setup-2fa-box">
        <p style="font-weight:500;margin-bottom:.5rem">1. Escanea este código QR con tu app</p>
        <div class="qr-placeholder">
          <img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(data.uri)}" width="150" height="150" alt="QR 2FA" style="border-radius:4px">
        </div>
        <p style="font-size:.85rem;color:var(--gris);margin-bottom:.5rem">O ingresa este código manualmente:</p>
        <div class="secret-code">${data.secret}</div>
      </div>
      <p style="font-size:.85rem;color:var(--texto2);margin-bottom:.7rem">2. Ingresa el código de 6 dígitos para confirmar:</p>
      <div style="display:flex;gap:.7rem">
        <input type="text" id="verify-totp-code" maxlength="6" placeholder="123456" style="padding:.6rem .9rem;border:1.5px solid var(--borde);border-radius:8px;font-size:1rem;outline:none;flex:1;letter-spacing:.2em;text-align:center">
        <button class="btn btn-primary" onclick="verificar2FA()">Verificar</button>
      </div>`;
  } catch (e) { toast(e.message, 'error'); }
}

async function verificar2FA() {
  const code = v('verify-totp-code').value.replace(/\D/g, '');
  if (code.length !== 6) { toast('Ingresa el código de 6 dígitos', 'error'); return; }
  try {
    await post('/auth/2fa/verify', { code });
    state.usuario.totp_enabled = true;
    document.getElementById('badge-2fa').style.display = 'inline-block';
    toast('✅ 2FA activado correctamente');
    cargarSeguridad();
  } catch (e) { toast(e.message, 'error'); }
}

async function desactivar2FA() {
  if (!confirm('¿Desactivar la autenticación de 2 factores? Tu cuenta quedará menos protegida.')) return;
  try {
    await del('/auth/2fa/disable');
    state.usuario.totp_enabled = false;
    document.getElementById('badge-2fa').style.display = 'none';
    toast('2FA desactivado');
    cargarSeguridad();
  } catch (e) { toast(e.message, 'error'); }
}

// ══════════════════════════════════════════════════════════════════
//  AUDITORÍA
// ══════════════════════════════════════════════════════════════════
async function cargarAuditoria() {
  const logs = await get('/reportes/audit-log?limit=100').catch(() => []);
  document.getElementById('tabla-auditoria').innerHTML = logs.map(l => `
    <tr>
      <td style="white-space:nowrap;font-size:.8rem">${l.timestamp?.slice(0, 19).replace('T', ' ')}</td>
      <td>${l.usuario ? `<code style="font-size:.8rem">@${l.usuario}</code>` : '—'}</td>
      <td><span class="badge ${l.accion.includes('FALLIDO') || l.accion.includes('BLOQUEADA') ? 'badge-danger' : 'badge-verde'}">${l.accion}</span></td>
      <td>${l.tabla || '—'}</td>
      <td style="font-size:.8rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.detalle || '—'}</td>
      <td style="font-size:.8rem;color:var(--gris)">${l.ip || '—'}</td>
    </tr>`).join('') || `<tr><td colspan="6" class="table-empty">Sin registros</td></tr>`;
}

// ══════════════════════════════════════════════════════════════════
//  UTILS
// ══════════════════════════════════════════════════════════════════
function fmt(n) { return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(n || 0); }
function pct(val, max) { return max > 0 ? Math.max(2, (val / max * 100)).toFixed(0) : 0; }
function emptyChart(msg) { return `<p style="color:var(--gris);font-size:.9rem;padding:.5rem 0">${msg}</p>`; }
function v(id) { return document.getElementById(id); }
function abrirModal(id)  { document.getElementById(id).classList.add('open'); }
function cerrarModal(id) { document.getElementById(id).classList.remove('open'); }

function filtrarTablaLive(inputId, tbodyId) {
  const q = (v(inputId)?.value || '').toLowerCase();
  document.querySelectorAll(`#${tbodyId} tr`).forEach(tr => { tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none'; });
}

let toastTimer;
function toast(msg, tipo = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = `show ${tipo}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.className = '', 4500);
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
});
document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});

// Intentar restaurar sesión desde refresh token guardado
loadStoredTokens();
if (state.refreshToken) {
  tryRefreshToken().then(ok => {
    if (ok) get('/auth/me').then(me => { if (me) { state.usuario = me; onLoginSuccess({ access_token: state.accessToken, refresh_token: state.refreshToken, requires_2fa: false, user: me }); } });
  });
}
