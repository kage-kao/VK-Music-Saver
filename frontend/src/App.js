import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Music, Download, Clock, LogOut, Link2, Loader2, CheckCircle2,
  AlertCircle, Archive, Upload, Trash2, ExternalLink,
  Key, RefreshCw, History, Zap, Shield, Globe,
  Plus, Power, X, Info, Wifi, WifiOff, Activity,
  ListMusic, Music2, Tag, FileText, Settings2, Ban,
  ChevronDown, Copy, Check
} from "lucide-react";
import axios from "axios";
import "./App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ==================== LOGIN ====================
const LoginPage = ({ onLogin }) => {
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleTokenLogin = async () => {
    if (!token.trim()) { setError("Вставьте ваш VK токен"); return; }
    setLoading(true); setError("");
    try {
      const res = await axios.post(`${API}/vk/token-login`, { token: token.trim() });
      if (res.data.status === "success") onLogin(res.data.session_id, res.data.user);
    } catch (e) {
      setError(e.response?.data?.detail || "Неверный токен");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-3 sm:p-4" data-testid="login-page">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-blue-500/5 blur-[120px]" />
      </div>
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
              <Music className="w-6 h-6 text-blue-400" />
            </div>
            <h1 className="font-heading text-2xl font-bold">VK Music Saver</h1>
          </div>
          <p className="text-zinc-400 text-sm">Скачивайте плейлисты, треки и всю библиотеку из ВК</p>
        </div>
        <div className="glass-card rounded-2xl p-6" data-testid="login-card">
          <div className="flex items-center gap-2 mb-5">
            <Key className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold">Вход по токену</h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-zinc-400 mb-1.5">Токен доступа VK</label>
              <textarea data-testid="token-input" value={token} onChange={(e) => setToken(e.target.value)}
                placeholder="Вставьте ваш VK токен (Kate Mobile, VK Admin и т.д.)" rows={3}
                className="w-full px-4 py-3 rounded-xl bg-[#0f0f11] border border-zinc-800 text-white placeholder:text-zinc-600 focus:outline-none input-glow transition-all font-mono text-sm resize-none"
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleTokenLogin(); } }}
              />
            </div>
            <p className="text-xs text-zinc-500">Токен с правами доступа к аудио (Kate Mobile, VK Admin и т.д.)</p>
            {error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 rounded-lg p-3" data-testid="token-error">
                <AlertCircle className="w-4 h-4 flex-shrink-0" /><span>{error}</span>
              </motion.div>
            )}
            <button data-testid="token-login-button" onClick={handleTokenLogin} disabled={loading}
              className="w-full h-12 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-semibold flex items-center justify-center gap-2 transition-all btn-glow disabled:opacity-50">
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : (<>Войти по токену<Key className="w-4 h-4" /></>)}
            </button>
          </div>
        </div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mt-4">
          <a href="https://telegra.ph/Poluchenie-klyucha-tokena-API-02-18" target="_blank" rel="noopener noreferrer"
            data-testid="token-instruction-link"
            className="instruction-banner glass-card rounded-xl p-4 flex items-start gap-3 hover:border-blue-500/30 transition-all group">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Info className="w-4 h-4 text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-zinc-200 mb-1">Как получить токен</p>
              <p className="text-xs text-zinc-500 truncate group-hover:text-blue-400 transition-colors">telegra.ph/Poluchenie-klyucha-tokena-API-02-18</p>
            </div>
            <ExternalLink className="w-4 h-4 text-zinc-600 group-hover:text-blue-400 transition-colors flex-shrink-0 mt-1" />
          </a>
        </motion.div>
      </motion.div>
    </div>
  );
};


// ==================== PROXY STATUS BADGE ====================
const ProxyStatusBadge = ({ status, statusMessage, latency, ip }) => {
  const cfg = {
    ok: { dotClass: "ok", icon: <Wifi className="w-3 h-3" />, color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", label: "Работает" },
    error: { dotClass: "error", icon: <WifiOff className="w-3 h-3" />, color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20", label: "Ошибка" },
    checking: { dotClass: "checking", icon: <Loader2 className="w-3 h-3 animate-spin" />, color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20", label: "Проверка..." },
  }[status] || { dotClass: "unchecked", icon: <Activity className="w-3 h-3" />, color: "text-zinc-500", bg: "bg-zinc-800", border: "border-zinc-700", label: "Не проверен" };

  return (
    <div className="space-y-1.5">
      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md ${cfg.bg} border ${cfg.border}`}>
        <div className={`proxy-status-dot ${cfg.dotClass}`} />
        <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
      </div>
      {statusMessage && <p className={`text-xs ${status === "ok" ? "text-emerald-500/80" : status === "error" ? "text-red-400/80" : "text-zinc-500"}`}>{statusMessage}</p>}
      {status === "ok" && (latency > 0 || ip) && (
        <div className="flex items-center gap-3 text-xs text-zinc-500">
          {latency > 0 && <span className="flex items-center gap-1"><Activity className="w-3 h-3 text-emerald-500" />{latency}мс</span>}
          {ip && <span className="font-mono text-emerald-500/70">{ip}</span>}
        </div>
      )}
    </div>
  );
};


// ==================== PROXY SETTINGS MODAL ====================
const ProxySettings = ({ isOpen, onClose }) => {
  const [proxies, setProxies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newProxy, setNewProxy] = useState({ proxy_type: "vless", address: "", name: "" });
  const [addError, setAddError] = useState("");
  const [checking, setChecking] = useState("");

  const fetchProxies = useCallback(async () => {
    try { const res = await axios.get(`${API}/proxies`); setProxies(res.data || []); } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { if (isOpen) fetchProxies(); }, [isOpen, fetchProxies]);
  useEffect(() => { if (!checking) return; const i = setInterval(fetchProxies, 1000); return () => clearInterval(i); }, [checking, fetchProxies]);

  const handleAdd = async () => {
    if (!newProxy.address.trim()) { setAddError("Введите адрес прокси"); return; }
    setLoading(true); setAddError("");
    try {
      await axios.post(`${API}/proxies`, newProxy);
      setNewProxy({ proxy_type: "vless", address: "", name: "" }); setShowAdd(false); fetchProxies();
    } catch (e) { setAddError(e.response?.data?.detail || "Ошибка добавления прокси"); }
    finally { setLoading(false); }
  };

  const handleAddAndCheck = async () => {
    if (!newProxy.address.trim()) { setAddError("Введите адрес прокси"); return; }
    setLoading(true); setAddError("");
    try {
      const res = await axios.post(`${API}/proxies`, newProxy);
      const proxyId = res.data.id;
      setNewProxy({ proxy_type: "vless", address: "", name: "" }); setShowAdd(false); fetchProxies();
      setChecking(proxyId);
      try { await axios.post(`${API}/proxies/${proxyId}/check`); fetchProxies(); } catch (e) { fetchProxies(); }
      finally { setChecking(""); }
    } catch (e) { setAddError(e.response?.data?.detail || "Ошибка"); }
    finally { setLoading(false); }
  };

  const handleToggle = async (proxyId) => {
    try { await axios.post(`${API}/proxies/${proxyId}/toggle`); fetchProxies(); } catch (e) { console.error(e); }
  };

  const handleDelete = async (proxyId) => {
    try { await axios.delete(`${API}/proxies/${proxyId}`); fetchProxies(); } catch (e) { console.error(e); }
  };

  const handleCheck = async (proxyId) => {
    setChecking(proxyId);
    try { await axios.post(`${API}/proxies/${proxyId}/check`); fetchProxies(); } catch (e) { fetchProxies(); }
    finally { setChecking(""); }
  };

  if (!isOpen) return null;
  const activeProxy = proxies.find(p => p.enabled);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="proxy-settings-modal">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
        className="relative w-full sm:max-w-lg glass-card rounded-t-2xl sm:rounded-2xl overflow-hidden max-h-[90vh] sm:max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-800/50">
          <div className="flex items-center gap-2.5">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${activeProxy ? "bg-emerald-500/10 border border-emerald-500/20" : "bg-zinc-800 border border-zinc-700"}`}>
              <Globe className={`w-4 h-4 ${activeProxy ? "text-emerald-400" : "text-zinc-500"}`} />
            </div>
            <div>
              <h3 className="text-sm font-semibold">Настройки прокси</h3>
              <p className="text-xs text-zinc-500">
                {activeProxy ? <span className="text-emerald-400">Активен: {activeProxy.name}</span> : "Нет активного прокси"}
              </p>
            </div>
          </div>
          <button onClick={onClose} data-testid="close-proxy-settings" className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mx-4 sm:mx-5 mt-4 p-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
          <p className="text-xs text-zinc-400">
            <span className="text-blue-400 font-medium">Зачем прокси?</span> Сервер находится за пределами России, некоторые треки VK имеют региональные ограничения. Подключите российский прокси для доступа ко всем трекам. Прокси используется <span className="text-blue-400">только для загрузки из VK</span>, не для выгрузки на TempShare.
          </p>
        </div>

        {/* Proxy List */}
        <div className="p-4 sm:p-5 space-y-3 overflow-y-auto flex-1">
          {proxies.length === 0 && !showAdd && (
            <div className="text-center py-8" data-testid="no-proxies">
              <Shield className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
              <p className="text-sm text-zinc-500">Прокси не добавлены</p>
              <p className="text-xs text-zinc-600 mt-1">Добавьте HTTP, SOCKS5 или VLESS конфиг</p>
            </div>
          )}

          {proxies.map(proxy => (
            <div key={proxy.id} data-testid={`proxy-item-${proxy.id}`}
              className={`rounded-xl p-3.5 border transition-all ${proxy.enabled ? "bg-emerald-500/5 border-emerald-500/20" : "bg-zinc-900/50 border-zinc-800/50"}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2.5 min-w-0 flex-1">
                  <button onClick={() => handleToggle(proxy.id)} data-testid={`toggle-proxy-${proxy.id}`}
                    className={`mt-0.5 flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                      proxy.enabled
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 pulse-green"
                        : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700 hover:text-white"
                    }`}>
                    <Power className="w-3.5 h-3.5" />
                    {proxy.enabled ? "ВКЛ" : "ВЫКЛ"}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-medium uppercase tracking-wider text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">{proxy.proxy_type}</span>
                      <span className="text-sm font-medium truncate">{proxy.name}</span>
                      {proxy.enabled && proxy.xray_running && (
                        <span className="text-xs text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded">xray:{proxy.xray_port}</span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-600 font-mono truncate mb-2">
                      {proxy.proxy_type === "vless" ? proxy.address.substring(0, 50) + (proxy.address.length > 50 ? "..." : "") : proxy.address}
                    </p>
                    <ProxyStatusBadge status={checking === proxy.id ? "checking" : proxy.status}
                      statusMessage={proxy.status_message} latency={proxy.check_latency} ip={proxy.check_ip} />
                  </div>
                </div>
                <div className="flex flex-col gap-1 flex-shrink-0">
                  <button onClick={() => handleCheck(proxy.id)} data-testid={`check-proxy-${proxy.id}`} disabled={checking === proxy.id}
                    className={`px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                      checking === proxy.id ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20"
                    }`}>
                    {checking === proxy.id ? <><Loader2 className="w-3 h-3 animate-spin" />Тест</> : <><Activity className="w-3 h-3" />Тест</>}
                  </button>
                  <button onClick={() => handleDelete(proxy.id)} data-testid={`delete-proxy-${proxy.id}`}
                    className="px-2.5 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/20 transition-all flex items-center gap-1.5 justify-center">
                    <Trash2 className="w-3 h-3" />Удл
                  </button>
                </div>
              </div>
            </div>
          ))}

          {/* Add form */}
          <AnimatePresence>
            {showAdd && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 space-y-3" data-testid="add-proxy-form">
                <div className="flex gap-2">
                  {["vless", "socks5", "http"].map(type => (
                    <button key={type} data-testid={`proxy-type-${type}`} onClick={() => setNewProxy(p => ({ ...p, proxy_type: type }))}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium uppercase tracking-wider transition-all ${
                        newProxy.proxy_type === type ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-zinc-800 text-zinc-500 border border-transparent hover:text-zinc-300"
                      }`}>{type}</button>
                  ))}
                </div>
                <input data-testid="proxy-name-input" type="text" value={newProxy.name} onChange={e => setNewProxy(p => ({ ...p, name: e.target.value }))}
                  placeholder="Название (необязательно)" className="w-full h-10 px-3 rounded-lg bg-[#0f0f11] border border-zinc-800 text-white text-sm placeholder:text-zinc-600 focus:outline-none input-glow transition-all" />
                <textarea data-testid="proxy-address-input" value={newProxy.address} onChange={e => setNewProxy(p => ({ ...p, address: e.target.value }))}
                  placeholder={newProxy.proxy_type === "vless" ? "vless://uuid@server:port?type=tcp&security=tls..." : newProxy.proxy_type === "socks5" ? "ip:port или user:pass@ip:port" : "http://ip:port"}
                  rows={newProxy.proxy_type === "vless" ? 3 : 1}
                  className="w-full px-3 py-2.5 rounded-lg bg-[#0f0f11] border border-zinc-800 text-white text-sm font-mono placeholder:text-zinc-600 focus:outline-none input-glow transition-all resize-none" />
                {addError && <p className="text-xs text-red-400" data-testid="add-proxy-error">{addError}</p>}
                <div className="flex flex-wrap gap-2">
                  <button data-testid="save-proxy-button" onClick={handleAdd} disabled={loading}
                    className="h-9 px-3 sm:px-4 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-white text-xs sm:text-sm font-medium flex items-center justify-center gap-1.5 transition-all disabled:opacity-50">
                    {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Сохранить"}
                  </button>
                  <button data-testid="save-and-check-proxy-button" onClick={handleAddAndCheck} disabled={loading}
                    className="h-9 px-3 sm:px-4 rounded-lg bg-blue-500 hover:bg-blue-600 text-white text-xs sm:text-sm font-medium flex items-center justify-center gap-1.5 transition-all disabled:opacity-50">
                    {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : (<><Activity className="w-3.5 h-3.5" /><span className="hidden sm:inline">Сохранить и</span> проверить</>)}
                  </button>
                  <button data-testid="cancel-add-proxy" onClick={() => { setShowAdd(false); setAddError(""); }}
                    className="h-9 px-3 rounded-lg bg-zinc-800 text-zinc-400 text-xs sm:text-sm hover:text-white transition-colors">Отмена</button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="p-4 sm:p-5 border-t border-zinc-800/50">
          {!showAdd && (
            <button data-testid="add-proxy-button" onClick={() => setShowAdd(true)}
              className="w-full h-10 rounded-xl border border-dashed border-zinc-700 text-zinc-400 hover:text-white hover:border-blue-500/30 text-sm flex items-center justify-center gap-2 transition-all">
              <Plus className="w-4 h-4" />Добавить прокси
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
};


// ==================== STATUS HELPERS ====================
const statusLabels = {
  pending: "В очереди", downloading: "Скачивание", zipping: "Создание архива",
  uploading: "Загрузка", completed: "Готово", error: "Ошибка", cancelled: "Отменено", cancelling: "Отмена..."
};

const StatusIcon = ({ status }) => {
  const icons = {
    pending: <Clock className="w-4 h-4" />, downloading: <Download className="w-4 h-4 animate-bounce" />,
    zipping: <Archive className="w-4 h-4" />, uploading: <Upload className="w-4 h-4" />,
    completed: <CheckCircle2 className="w-4 h-4" />, error: <AlertCircle className="w-4 h-4" />,
    cancelled: <Ban className="w-4 h-4" />, cancelling: <Loader2 className="w-4 h-4 animate-spin" />,
  };
  return <span className={`status-${status}`}>{icons[status] || icons.pending}</span>;
};

const SegmentedProgress = ({ progress, status }) => {
  const segments = 20;
  const filled = Math.floor((progress / 100) * segments);
  return (
    <div className="progress-segmented" data-testid="progress-bar">
      {Array.from({ length: segments }).map((_, i) => (
        <div key={i} className={`progress-segment ${i < filled ? (status === "completed" ? "completed" : "active") : ""}`} />
      ))}
    </div>
  );
};


// ==================== DOWNLOAD ITEM ====================
const DownloadItem = ({ task, onDelete, onCancel }) => {
  const isActive = ["pending", "downloading", "zipping", "uploading", "cancelling"].includes(task.status);
  const [copied, setCopied] = useState(null);

  const handleCopy = (url, idx) => {
    navigator.clipboard.writeText(url);
    setCopied(idx);
    setTimeout(() => setCopied(null), 1500);
  };

  const typeLabel = task.download_type === "my_music" ? "Моя музыка" : task.download_type === "track" ? "Трек" : "Плейлист";

  return (
    <motion.div layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
      className={`glass-card rounded-xl p-3 sm:p-4 ${task.status === "completed" ? "border-green-500/20" : task.status === "cancelled" ? "border-zinc-600/20" : ""}`}
      data-testid={`download-item-${task.id}`}>
      <div className="flex items-start justify-between gap-2 sm:gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <StatusIcon status={task.status} />
          <div className="min-w-0">
            <p className="text-xs sm:text-sm font-medium truncate">{task.playlist_title || "Загрузка..."}</p>
            <div className="flex items-center gap-1.5 sm:gap-2 text-xs text-zinc-500 mt-0.5 flex-wrap">
              <span className="bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400">{typeLabel}</span>
              <span className={`status-${task.status}`}>{statusLabels[task.status]}</span>
              {task.track_count > 0 && (
                <span className="hidden sm:inline">
                  {task.downloaded_count !== undefined && task.downloaded_count !== task.track_count
                    ? `${task.downloaded_count}/${task.track_count} треков`
                    : `${task.track_count} треков`}
                </span>
              )}
              {task.file_size && <span>{task.file_size}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {isActive && task.status !== "cancelling" && (
            <button onClick={() => onCancel(task.id)} data-testid={`cancel-task-${task.id}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors text-xs font-medium">
              <Ban className="w-3.5 h-3.5" />Отмена
            </button>
          )}
          {task.status === "completed" && task.download_urls && task.download_urls.length > 1 ? (
            <div className="flex flex-col gap-1">
              {task.download_urls.map((url, idx) => (
                <a key={idx} href={url} target="_blank" rel="noopener noreferrer" data-testid={`download-link-${task.id}-${idx}`}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors text-xs font-medium">
                  <ExternalLink className="w-3.5 h-3.5" />Часть {idx + 1}
                </a>
              ))}
            </div>
          ) : task.status === "completed" && task.download_url && (
            <a href={task.download_url} target="_blank" rel="noopener noreferrer" data-testid={`download-link-${task.id}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors text-xs font-medium">
              <ExternalLink className="w-3.5 h-3.5" />Скачать
            </a>
          )}
          {!isActive && (
            <button onClick={() => onDelete(task.id)} data-testid={`delete-task-${task.id}`}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors"><Trash2 className="w-3.5 h-3.5" /></button>
          )}
        </div>
      </div>

      {isActive && (
        <div className="space-y-2">
          <SegmentedProgress progress={task.progress || 0} status={task.status} />
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <span className="truncate max-w-[70%]">{task.current_track || ""}</span>
            <span>{Math.round(task.progress || 0)}%</span>
          </div>
        </div>
      )}

      {task.status === "error" && <div className="mt-2 text-xs text-red-400 bg-red-500/10 rounded-lg p-2" data-testid="task-error">{task.error_message}</div>}

      {task.status === "completed" && (
        <div className="mt-2 space-y-1">
          {(task.download_urls && task.download_urls.length > 0 ? task.download_urls : task.download_url ? [task.download_url] : []).map((url, idx) => (
            <div key={idx} className="flex items-center gap-2 font-mono text-xs text-zinc-500 bg-zinc-900 rounded-lg p-2">
              <span className="truncate flex-1">{url}</span>
              <button onClick={() => handleCopy(url, idx)} className="flex-shrink-0 p-1 rounded hover:bg-zinc-800 transition-colors" data-testid={`copy-url-${task.id}-${idx}`}>
                {copied === idx ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3 text-zinc-500" />}
              </button>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
};


// ==================== DASHBOARD ====================
const Dashboard = ({ sessionId, user, onLogout }) => {
  const [mode, setMode] = useState("playlist");
  const [inputUrl, setInputUrl] = useState("");
  const [multiUrls, setMultiUrls] = useState("");
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showProxySettings, setShowProxySettings] = useState(false);
  const [activeProxyStatus, setActiveProxyStatus] = useState(null);

  const [addTags, setAddTags] = useState(false);
  const [addLyrics, setAddLyrics] = useState(false);
  const [quality, setQuality] = useState("high");
  const [showOptions, setShowOptions] = useState(false);

  const fetchTasks = useCallback(async () => {
    try {
      const [activeRes, historyRes] = await Promise.all([
        axios.get(`${API}/download/active/${sessionId}`),
        axios.get(`${API}/download/history/${sessionId}`)
      ]);
      const activeTasks = activeRes.data || [];
      const allTasks = historyRes.data || [];
      const activeIds = new Set(activeTasks.map(t => t.id));
      const completedTasks = allTasks.filter(t => !activeIds.has(t.id));
      setTasks([...activeTasks, ...completedTasks]);
    } catch (e) { console.error(e); }
  }, [sessionId]);

  const fetchProxyStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/proxies`);
      const active = (res.data || []).find(p => p.enabled);
      setActiveProxyStatus(active || null);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    fetchTasks(); fetchProxyStatus();
    const i1 = setInterval(fetchTasks, 2000);
    const i2 = setInterval(fetchProxyStatus, 5000);
    return () => { clearInterval(i1); clearInterval(i2); };
  }, [fetchTasks, fetchProxyStatus]);

  const handleDownload = async () => {
    setLoading(true); setError("");
    try {
      const opts = { add_tags: addTags, add_lyrics: addLyrics, quality };
      if (mode === "playlist") {
        if (!inputUrl.trim()) { setError("Вставьте ссылку на плейлист"); setLoading(false); return; }
        await axios.post(`${API}/download/start`, { session_id: sessionId, playlist_url: inputUrl, ...opts });
        setInputUrl("");
      } else if (mode === "track") {
        if (!inputUrl.trim()) { setError("Вставьте ссылку на трек"); setLoading(false); return; }
        await axios.post(`${API}/download/track`, { session_id: sessionId, track_url: inputUrl, ...opts });
        setInputUrl("");
      } else if (mode === "my_music") {
        await axios.post(`${API}/download/my-music`, { session_id: sessionId, ...opts });
      } else if (mode === "multi") {
        const urls = multiUrls.split('\n').map(u => u.trim()).filter(Boolean);
        if (urls.length === 0) { setError("Вставьте ссылки на плейлисты (по одной на строку)"); setLoading(false); return; }
        await axios.post(`${API}/download/multi`, { session_id: sessionId, playlist_urls: urls, ...opts });
        setMultiUrls("");
      }
      fetchTasks();
    } catch (e) {
      setError(e.response?.data?.detail || "Ошибка загрузки");
    } finally { setLoading(false); }
  };

  const handleDelete = async (taskId) => {
    try { await axios.delete(`${API}/download/${taskId}`); setTasks(prev => prev.filter(t => t.id !== taskId)); } catch (e) { console.error(e); }
  };

  const handleCancel = async (taskId) => {
    try { await axios.post(`${API}/download/cancel/${taskId}`); fetchTasks(); } catch (e) { console.error(e); }
  };

  const activeTasks = tasks.filter(t => ["pending", "downloading", "zipping", "uploading", "cancelling"].includes(t.status));
  const completedTasks = tasks.filter(t => ["completed", "error", "cancelled"].includes(t.status));

  const modes = [
    { id: "playlist", label: "Плейлист", icon: <ListMusic className="w-4 h-4" /> },
    { id: "track", label: "Трек", icon: <Music2 className="w-4 h-4" /> },
    { id: "my_music", label: "Моя музыка", icon: <Music className="w-4 h-4" /> },
    { id: "multi", label: "Несколько", icon: <Archive className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen" data-testid="dashboard">
      <header className="border-b border-zinc-800/50 bg-[#09090b]/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-3 sm:px-4 h-14 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
              <Music className="w-4 h-4 text-blue-400" />
            </div>
            <span className="font-heading text-sm font-semibold hidden sm:inline">VK Music Saver</span>
          </div>
          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
            <button onClick={() => setShowProxySettings(true)} data-testid="open-proxy-settings"
              className={`flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1.5 rounded-lg transition-all ${
                activeProxyStatus ? "bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/15" : "hover:bg-zinc-800 border border-zinc-700"
              }`}>
              <div className={`proxy-status-dot ${activeProxyStatus ? (activeProxyStatus.status === "ok" ? "ok" : "unchecked") : "unchecked"}`} />
              <Globe className={`w-4 h-4 ${activeProxyStatus ? "text-emerald-400" : "text-zinc-500"}`} />
              {activeProxyStatus ? (
                <span className="text-xs text-emerald-400 hidden sm:inline">{activeProxyStatus.name}</span>
              ) : (
                <span className="text-xs text-zinc-500 hidden sm:inline">Прокси</span>
              )}
            </button>
            {user?.photo && <img src={user.photo} alt="" className="w-7 h-7 rounded-full border border-zinc-700 hidden sm:block" data-testid="user-avatar" />}
            <span className="text-sm text-zinc-400 hidden sm:inline" data-testid="user-name">{user?.first_name} {user?.last_name}</span>
            <button onClick={onLogout} data-testid="logout-button" className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-3 sm:px-4 py-4 sm:py-8">
        {/* Download Section */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <div className="relative">
            <div className="absolute inset-0 bg-blue-500/5 rounded-2xl blur-xl" />
            <div className="glass-card rounded-2xl p-4 sm:p-6 relative" data-testid="download-section">
              {/* Mode selector */}
              <div className="flex gap-1 mb-5 p-1 bg-zinc-900/80 rounded-xl w-full sm:w-fit overflow-x-auto scrollbar-hide" data-testid="mode-selector">
                {modes.map(m => (
                  <button key={m.id} data-testid={`mode-${m.id}`} onClick={() => { setMode(m.id); setError(""); }}
                    className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap flex-shrink-0 ${
                      mode === m.id ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "text-zinc-500 hover:text-zinc-300"
                    }`}>
                    {m.icon}<span className="hidden xs:inline sm:inline">{m.label}</span>
                  </button>
                ))}
              </div>

              {/* Input area based on mode */}
              {mode === "my_music" ? (
                <div className="mb-4">
                  <p className="text-sm text-zinc-300 mb-1">Скачать всю вашу музыкальную библиотеку VK</p>
                  <p className="text-xs text-zinc-500">Все сохранённые треки будут скачаны, заархивированы и загружены на TempShare</p>
                </div>
              ) : mode === "multi" ? (
                <div className="mb-4">
                  <p className="text-sm text-zinc-300 mb-2">Вставьте ссылки на плейлисты (по одной на строку)</p>
                  <textarea data-testid="multi-url-input" value={multiUrls} onChange={(e) => setMultiUrls(e.target.value)}
                    placeholder={"https://vk.com/music?z=audio_playlist...\nhttps://vk.com/music?z=audio_playlist..."}
                    rows={4} className="w-full px-3 sm:px-4 py-3 rounded-xl bg-[#0f0f11] border border-zinc-800 text-white placeholder:text-zinc-600 focus:outline-none input-glow transition-all font-mono text-xs sm:text-sm resize-none" />
                </div>
              ) : (
                <div className="flex flex-col sm:flex-row gap-3 mb-4">
                  <div className="flex-1 relative">
                    <Link2 className="absolute left-3 sm:left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                    <input data-testid="url-input" type="text" value={inputUrl} onChange={(e) => setInputUrl(e.target.value)}
                      placeholder={mode === "track" ? "https://vk.com/audio-2001..._456..." : "https://vk.com/music?z=audio_playlist..."}
                      className="w-full h-11 sm:h-12 pl-9 sm:pl-10 pr-3 sm:pr-4 rounded-xl bg-[#0f0f11] border border-zinc-800 text-white placeholder:text-zinc-600 focus:outline-none input-glow transition-all font-mono text-xs sm:text-sm"
                      onKeyDown={(e) => e.key === 'Enter' && handleDownload()} />
                  </div>
                </div>
              )}

              {/* Options toggle */}
              <div className="flex items-center justify-between mb-4">
                <button data-testid="toggle-options" onClick={() => setShowOptions(!showOptions)}
                  className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white transition-colors">
                  <Settings2 className="w-3.5 h-3.5" />
                  <span>Настройки</span>
                  <ChevronDown className={`w-3 h-3 transition-transform ${showOptions ? "rotate-180" : ""}`} />
                </button>
              </div>

              {/* Options panel */}
              <AnimatePresence>
                {showOptions && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    className="mb-4 overflow-hidden">
                    <div className="flex flex-wrap gap-2 sm:gap-3 items-center p-3 rounded-xl bg-zinc-900/60 border border-zinc-800/50">
                      <button data-testid="toggle-tags" onClick={() => setAddTags(!addTags)}
                        className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-lg text-xs font-medium transition-all ${
                          addTags ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300"
                        }`}>
                        <Tag className="w-3.5 h-3.5" />ID3 теги
                        {addTags && <Check className="w-3 h-3" />}
                      </button>
                      <button data-testid="toggle-lyrics" onClick={() => setAddLyrics(!addLyrics)}
                        className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 sm:py-2 rounded-lg text-xs font-medium transition-all ${
                          addLyrics ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300"
                        }`}>
                        <FileText className="w-3.5 h-3.5" />Тексты
                        {addLyrics && <Check className="w-3 h-3" />}
                      </button>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-zinc-500 hidden sm:inline">Качество:</span>
                        {["low", "medium", "high"].map(q => (
                          <button key={q} data-testid={`quality-${q}`} onClick={() => setQuality(q)}
                            className={`px-2 sm:px-2.5 py-1 sm:py-1.5 rounded-lg text-xs font-medium transition-all ${
                              quality === q ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300"
                            }`}>{q === "low" ? "128" : q === "medium" ? "256" : "320"}</button>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Download button */}
              <button data-testid="download-button" onClick={handleDownload} disabled={loading}
                className="w-full h-12 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-semibold flex items-center justify-center gap-2 transition-all btn-glow disabled:opacity-50">
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : (
                  <>
                    <Download className="w-4 h-4" />
                    {mode === "my_music" ? "Скачать мою музыку" : mode === "multi" ? "Скачать все" : mode === "track" ? "Скачать трек" : "Скачать плейлист"}
                  </>
                )}
              </button>

              {error && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 text-red-400 text-sm mt-3" data-testid="download-error">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" /><span>{error}</span>
                </motion.div>
              )}
            </div>
          </div>
        </motion.div>

        {/* Active Downloads */}
        {activeTasks.length > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="w-4 h-4 text-blue-400" />
              <h3 className="text-sm font-semibold text-zinc-300">Активные загрузки</h3>
              <span className="text-xs bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full">{activeTasks.length}</span>
            </div>
            <div className="space-y-3" data-testid="active-downloads">
              <AnimatePresence>
                {activeTasks.map(task => (<DownloadItem key={task.id} task={task} onDelete={handleDelete} onCancel={handleCancel} />))}
              </AnimatePresence>
            </div>
          </motion.div>
        )}

        {/* History */}
        <div className="flex items-center justify-between mb-4">
          <button data-testid="toggle-history" onClick={() => setShowHistory(!showHistory)} className="flex items-center gap-2 text-sm text-zinc-400 hover:text-white transition-colors">
            <History className="w-4 h-4" /><span>История загрузок</span>
            {completedTasks.length > 0 && <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded-full">{completedTasks.length}</span>}
          </button>
          <button onClick={fetchTasks} data-testid="refresh-button" className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        <AnimatePresence>
          {(showHistory || completedTasks.length === 0) && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
              {completedTasks.length > 0 ? (
                <div className="space-y-3" data-testid="completed-downloads">
                  <AnimatePresence>
                    {completedTasks.map(task => (<DownloadItem key={task.id} task={task} onDelete={handleDelete} onCancel={handleCancel} />))}
                  </AnimatePresence>
                </div>
              ) : activeTasks.length === 0 && (
                <div className="text-center py-16" data-testid="empty-state">
                  <div className="w-16 h-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto mb-4">
                    <Music className="w-8 h-8 text-zinc-600" />
                  </div>
                  <p className="text-zinc-500 text-sm">Пока ничего нет</p>
                  <p className="text-zinc-600 text-xs mt-1">Выберите режим и начните скачивание</p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {showProxySettings && (
          <ProxySettings isOpen={showProxySettings} onClose={() => { setShowProxySettings(false); fetchProxyStatus(); }} />
        )}
      </AnimatePresence>
    </div>
  );
};


// ==================== APP ====================
function App() {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("vk_session_id") || "");
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem("vk_user");
    return stored ? JSON.parse(stored) : null;
  });

  const handleLogin = (newSessionId, newUser) => {
    setSessionId(newSessionId);
    setUser(newUser);
    localStorage.setItem("vk_session_id", newSessionId);
    localStorage.setItem("vk_user", JSON.stringify(newUser));
  };

  const handleLogout = async () => {
    try { await axios.post(`${API}/vk/logout`, { session_id: sessionId }); } catch (e) {}
    setSessionId(""); setUser(null);
    localStorage.removeItem("vk_session_id"); localStorage.removeItem("vk_user");
  };

  return (
    <div className="App">
      {sessionId && user ? (
        <Dashboard sessionId={sessionId} user={user} onLogout={handleLogout} />
      ) : (
        <LoginPage onLogin={handleLogin} />
      )}
    </div>
  );
}

export default App;
