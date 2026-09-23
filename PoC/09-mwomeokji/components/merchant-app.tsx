"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  ClipboardList,
  LogOut,
  Menu as MenuIcon,
  Plus,
  RefreshCw,
  Sparkles,
  Store,
  X,
} from "lucide-react";
import { api, money } from "../lib/client";
import { ALLERGENS, type MenuItemData } from "../lib/types";

type Order = {
  id: string;
  code: string;
  status: string;
  total: number;
  note: string;
  createdAt: string;
  table: { label: string } | null;
  lines: {
    id: string;
    menuName: string;
    quantity: number;
    optionNames: string[];
    lineTotal: number;
  }[];
};
type Help = {
  id: string;
  status: string;
  note: string;
  createdAt: string;
  table: { label: string } | null;
};
type Dashboard = {
  store: { name: string; categories: { id: string; name: string }[] };
  menu: MenuItemData[];
  orders: Order[];
  helpRequests: Help[];
};
type EditData = {
  id?: string;
  name: string;
  description: string;
  categoryId: string;
  price: number;
  emoji: string;
  spiceLevel: number;
  isAvailable: boolean;
  isPublished: boolean;
  isShareable: boolean;
  tags: string[];
  ingredients: string[];
  dietaryTags: string[];
  allergens: {
    allergenKey: string;
    relation: "contains" | "excludes" | "unknown";
    verificationStatus: "merchant_verified" | "unknown";
  }[];
};
type OptionDraft = {
  name: string;
  minSelect: number;
  maxSelect: number;
  options: {
    name: string;
    priceDelta: number;
    isAvailable: boolean;
    ingredients: string[];
    dietaryTags: string[];
    allergens: EditData["allergens"];
  }[];
};
const newOption = () => ({
  name: "",
  priceDelta: 0,
  isAvailable: true,
  ingredients: [] as string[],
  dietaryTags: [] as string[],
  allergens: ALLERGENS.map(([allergenKey]) => ({
    allergenKey,
    relation: "unknown" as const,
    verificationStatus: "unknown" as const,
  })),
});
const newGroup = (): OptionDraft => ({
  name: "",
  minSelect: 0,
  maxSelect: 1,
  options: [newOption()],
});
const statusLabel: Record<string, string> = {
  placed: "새 주문",
  accepted: "접수",
  preparing: "조리 중",
  ready: "준비 완료",
  completed: "전달 완료",
  cancelled: "취소",
};
const blank = (categoryId = ""): EditData => ({
  name: "",
  description: "",
  categoryId,
  price: 0,
  emoji: "🍽️",
  spiceLevel: 0,
  isAvailable: true,
  isPublished: false,
  isShareable: false,
  tags: [],
  ingredients: [],
  dietaryTags: [],
  allergens: ALLERGENS.map(([allergenKey]) => ({
    allergenKey,
    relation: "unknown",
    verificationStatus: "unknown",
  })),
});
const fromMenu = (item: MenuItemData): EditData => ({
  id: item.id,
  name: item.name,
  description: item.description,
  categoryId: item.categoryId,
  price: item.price,
  emoji: item.emoji,
  spiceLevel: item.spiceLevel,
  isAvailable: item.isAvailable,
  isPublished: item.isPublished,
  isShareable: item.isShareable,
  tags: item.tags,
  ingredients: item.ingredients,
  dietaryTags: item.dietaryTags,
  allergens: ALLERGENS.map(([allergenKey]) => {
    const found = item.allergens.find(
      (entry) => entry.allergenKey === allergenKey,
    );
    return {
      allergenKey,
      relation:
        (found?.relation as "contains" | "excludes" | "unknown") || "unknown",
      verificationStatus:
        (found?.verificationStatus as "merchant_verified" | "unknown") ||
        "unknown",
    };
  }),
});

export function MerchantApp() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tab, setTab] = useState<"orders" | "menu" | "import">("orders");
  const [edit, setEdit] = useState<EditData | null>(null);
  const [optionDraft, setOptionDraft] = useState<OptionDraft>(newGroup);
  const [importText, setImportText] = useState("");
  const [importCategory, setImportCategory] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function load() {
    try {
      const data = await api<Dashboard>("merchant/dashboard");
      setDashboard(data);
      setLoggedIn(true);
      setImportCategory((value) => value || data.store.categories[0]?.id || "");
    } catch {
      setLoggedIn(false);
    }
  }
  useEffect(() => {
    const initial = setTimeout(() => {
      void load();
    }, 0);
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 12000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, []);
  async function login(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("merchant/login", "POST", { email, password });
      setPassword("");
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    await api("merchant/logout", "POST");
    setDashboard(null);
    setLoggedIn(false);
  }
  async function changeOrder(id: string, status: string) {
    try {
      await api(`merchant/orders/${id}`, "PATCH", { status });
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  async function resolveHelp(id: string) {
    try {
      await api(`merchant/help/${id}`, "PATCH", { status: "resolved" });
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  async function saveMenu() {
    if (!edit) return;
    setBusy(true);
    setError("");
    try {
      await api(
        `merchant/menu${edit.id ? `/${edit.id}` : ""}`,
        edit.id ? "PATCH" : "POST",
        edit,
      );
      setEdit(null);
      setSuccess("메뉴를 저장했어요.");
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggleMenu(
    item: MenuItemData,
    field: "isPublished" | "isAvailable",
  ) {
    try {
      await api(`merchant/menu/${item.id}`, "PATCH", { [field]: !item[field] });
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  function updateOption(
    index: number,
    patch: Partial<OptionDraft["options"][number]>,
  ) {
    setOptionDraft((current) => ({
      ...current,
      options: current.options.map((option, position) =>
        position === index ? { ...option, ...patch } : option,
      ),
    }));
  }
  function updateOptionAllergen(
    index: number,
    key: string,
    relation: "contains" | "excludes" | "unknown",
  ) {
    setOptionDraft((current) => ({
      ...current,
      options: current.options.map((option, position) =>
        position === index
          ? {
              ...option,
              allergens: option.allergens.map((allergen) =>
                allergen.allergenKey === key
                  ? {
                      ...allergen,
                      relation,
                      verificationStatus:
                        relation === "unknown"
                          ? "unknown"
                          : "merchant_verified",
                    }
                  : allergen,
              ),
            }
          : option,
      ),
    }));
  }
  async function addGroup() {
    if (!edit?.id) return;
    try {
      await api(`merchant/menu/${edit.id}/options`, "POST", optionDraft);
      setOptionDraft(newGroup());
      setSuccess("옵션을 저장했어요.");
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  async function removeGroup(groupId: string) {
    if (!edit?.id) return;
    try {
      await api(`merchant/menu/${edit.id}/options/${groupId}`, "DELETE");
      setSuccess("옵션 그룹을 삭제했어요.");
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    }
  }
  async function importMenu(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.set("categoryId", importCategory);
      form.set("text", importText);
      if (importFile) form.set("file", importFile);
      const result = await api<{ created: { id: string }[]; note: string }>(
        "merchant/import",
        "POST",
        form,
      );
      setImportText("");
      setImportFile(null);
      setSuccess(
        `${result.created.length}개 메뉴를 초안으로 저장했어요. 재료와 알레르기를 확인해 주세요.`,
      );
      setTab("menu");
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="merchant-app">
      <header className="app-header">
        <Link href="/" className="brand">
          <span className="brand-mark">ㅁㅁㅈ</span>
          <span>사장님</span>
        </Link>
        <div className="header-actions">
          <Link className="header-link" href="/s/orange-table">
            손님 화면 <ArrowRight size={16} />
          </Link>
          {loggedIn && (
            <button className="icon-button" onClick={logout} title="로그아웃">
              <LogOut size={19} />
            </button>
          )}
        </div>
      </header>
      {loggedIn === false ? (
        <main className="login-page">
          <div className="login-card">
            <div className="login-icon">
              <Store size={31} />
            </div>
            <span className="mini-label">MERCHANT STUDIO</span>
            <h1>어서 오세요, 사장님!</h1>
            <p>메뉴를 관리하고 새 주문을 확인해 보세요.</p>
            <form onSubmit={login}>
              <label>
                이메일
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="username"
                  required
                  placeholder="사장님 이메일"
                />
              </label>
              <label>
                비밀번호
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  placeholder="비밀번호"
                />
              </label>
              {error && (
                <p className="danger-text" role="alert">
                  {error}
                </p>
              )}
              <button className="button button-primary full" disabled={busy}>
                로그인 <ArrowRight size={18} />
              </button>
            </form>
            <small>
              데모 계정은 루트 .env의 POC09_MERCHANT_EMAIL / PASSWORD에 설정돼
              있어요.
            </small>
          </div>
        </main>
      ) : loggedIn === null ? (
        <main className="loading-page">매장 정보를 불러오는 중…</main>
      ) : (
        <main className="merchant-shell">
          <div className="merchant-welcome">
            <div>
              <span className="mini-label">STORE CONTROL</span>
              <h1>{dashboard?.store.name} 관리</h1>
              <p>새 주문부터 메뉴 확인까지 이곳에서 관리해요.</p>
            </div>
            <button className="button button-outline" onClick={load}>
              <RefreshCw size={16} /> 새로고침
            </button>
          </div>
          {error && (
            <div className="notice notice-error" role="alert">
              {error}
              <button onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {success && (
            <div className="notice notice-success" role="status">
              {success}
              <button onClick={() => setSuccess("")}>
                <X size={16} />
              </button>
            </div>
          )}
          <div className="stat-grid">
            <div>
              <span>새 주문</span>
              <strong>
                {dashboard?.orders.filter((order) => order.status === "placed")
                  .length || 0}
              </strong>
              <small>접수 대기 중</small>
            </div>
            <div>
              <span>직원 호출</span>
              <strong>
                {dashboard?.helpRequests.filter(
                  (help) => help.status === "open",
                ).length || 0}
              </strong>
              <small>확인해 주세요</small>
            </div>
            <div>
              <span>판매 중 메뉴</span>
              <strong>
                {dashboard?.menu.filter(
                  (item) => item.isPublished && item.isAvailable,
                ).length || 0}
              </strong>
              <small>손님 화면에 표시</small>
            </div>
          </div>
          <nav className="tabs merchant-tabs">
            <button
              className={tab === "orders" ? "active" : ""}
              onClick={() => setTab("orders")}
            >
              <ClipboardList size={17} /> 주문 · 호출
            </button>
            <button
              className={tab === "menu" ? "active" : ""}
              onClick={() => setTab("menu")}
            >
              <MenuIcon size={17} /> 메뉴 관리
            </button>
            <button
              className={tab === "import" ? "active" : ""}
              onClick={() => setTab("import")}
            >
              <Sparkles size={17} /> 메뉴판 가져오기
            </button>
          </nav>
          {tab === "orders" && (
            <div className="dashboard-columns">
              <section>
                <div className="section-heading">
                  <div>
                    <span className="mini-label">LIVE ORDERS</span>
                    <h2>들어온 주문</h2>
                  </div>
                </div>
                {dashboard?.orders.length ? (
                  <div className="merchant-order-list">
                    {dashboard.orders.map((order) => (
                      <article className="merchant-order" key={order.id}>
                        <div className="merchant-order-top">
                          <span className="order-status">
                            {statusLabel[order.status] || order.status}
                          </span>
                          <span>{order.table?.label || "테이블 미선택"}</span>
                          <time>
                            {new Date(order.createdAt).toLocaleTimeString(
                              "ko-KR",
                              { hour: "2-digit", minute: "2-digit" },
                            )}
                          </time>
                        </div>
                        <strong>{order.code}</strong>
                        {order.lines.map((line) => (
                          <p key={line.id}>
                            {line.menuName} × {line.quantity}
                            {line.optionNames.length > 0 && (
                              <small> · {line.optionNames.join(", ")}</small>
                            )}
                            <b>{money(line.lineTotal)}</b>
                          </p>
                        ))}
                        {order.note && (
                          <div className="order-note">요청: {order.note}</div>
                        )}
                        <div className="merchant-order-footer">
                          <strong>합계 {money(order.total)}</strong>
                          <select
                            value={order.status}
                            onChange={(event) =>
                              changeOrder(order.id, event.target.value)
                            }
                            aria-label={`${order.code} 주문 상태`}
                          >
                            {Object.entries(statusLabel).map(
                              ([value, label]) => (
                                <option key={value} value={value}>
                                  {label}
                                </option>
                              ),
                            )}
                          </select>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">아직 들어온 주문이 없어요.</div>
                )}
              </section>
              <aside>
                <div className="section-heading">
                  <div>
                    <span className="mini-label">HELP REQUESTS</span>
                    <h2>직원 호출</h2>
                  </div>
                </div>
                {dashboard?.helpRequests.filter(
                  (help) => help.status === "open",
                ).length ? (
                  dashboard.helpRequests
                    .filter((help) => help.status === "open")
                    .map((help) => (
                      <article className="help-card" key={help.id}>
                        <strong>{help.table?.label || "테이블 미선택"}</strong>
                        <time>
                          {new Date(help.createdAt).toLocaleTimeString("ko-KR")}
                        </time>
                        <p>{help.note}</p>
                        <button
                          className="button button-outline"
                          onClick={() => resolveHelp(help.id)}
                        >
                          <Check size={16} /> 처리 완료
                        </button>
                      </article>
                    ))
                ) : (
                  <div className="empty-state">대기 중인 호출이 없어요.</div>
                )}
              </aside>
            </div>
          )}
          {tab === "menu" && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <span className="mini-label">MENU CONTROL</span>
                  <h2>메뉴 관리</h2>
                </div>
                <button
                  className="button button-primary"
                  onClick={() =>
                    setEdit(blank(dashboard?.store.categories[0]?.id))
                  }
                >
                  <Plus size={18} /> 새 메뉴
                </button>
              </div>
              <div className="merchant-menu-grid">
                {dashboard?.menu.map((item) => (
                  <article className="merchant-menu-card" key={item.id}>
                    <span className="menu-emoji">{item.emoji}</span>
                    <div>
                      <strong>{item.name}</strong>
                      <small>{item.description}</small>
                      <b>{money(item.price)}</b>
                    </div>
                    <div className="merchant-menu-actions">
                      <button
                        className="button button-outline"
                        onClick={() => setEdit(fromMenu(item))}
                      >
                        수정
                      </button>
                      <button
                        className={`small-toggle ${item.isPublished ? "on" : ""}`}
                        onClick={() => toggleMenu(item, "isPublished")}
                      >
                        {item.isPublished ? "공개 중" : "초안"}
                      </button>
                      <button
                        className={`small-toggle ${item.isAvailable ? "on" : ""}`}
                        onClick={() => toggleMenu(item, "isAvailable")}
                      >
                        {item.isAvailable ? "판매 중" : "품절"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
          {tab === "import" && (
            <section className="import-layout">
              <div>
                <span className="mini-label">MENU ONBOARDING</span>
                <h2>메뉴판을 한 번에 가져와요</h2>
                <p>
                  메뉴를 초안으로 저장합니다. 사장님이 가격, 재료, 알레르기
                  정보를 확인한 뒤 공개해 주세요.
                </p>
                <div className="import-example">
                  햇살 덮밥 | 10900 | 달콤한 닭고기 덮밥
                  <br />
                  오렌지 에이드 | 4500 | 상큼한 탄산 음료
                </div>
              </div>
              <form className="import-form" onSubmit={importMenu}>
                <label>
                  카테고리
                  <select
                    value={importCategory}
                    onChange={(event) => setImportCategory(event.target.value)}
                  >
                    {dashboard?.store.categories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  메뉴 텍스트
                  <textarea
                    rows={8}
                    placeholder="메뉴명 | 가격 | 설명&#10;한 줄에 하나씩 입력해 주세요"
                    value={importText}
                    onChange={(event) => setImportText(event.target.value)}
                  />
                </label>
                <label>
                  메뉴판 사진 (선택)
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={(event) =>
                      setImportFile(event.target.files?.[0] || null)
                    }
                  />
                </label>
                <p className="fine-print">
                  이미지 자동 인식은 루트 .env에서 OpenRouter AI를 켰을 때
                  사용돼요.
                </p>
                <button
                  className="button button-primary full"
                  disabled={busy || (!importText.trim() && !importFile)}
                >
                  초안 만들기 <ArrowRight size={18} />
                </button>
              </form>
            </section>
          )}
        </main>
      )}
      {edit && (
        <div className="modal-backdrop" onClick={() => setEdit(null)}>
          <div
            className="menu-editor"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="panel-head">
              <div>
                <span className="mini-label">MENU EDITOR</span>
                <h2>{edit.id ? "메뉴 수정" : "새 메뉴 만들기"}</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setEdit(null)}
                aria-label="닫기"
              >
                <X />
              </button>
            </div>
            <div className="editor-grid">
              <label>
                메뉴명
                <input
                  value={edit.name}
                  onChange={(event) =>
                    setEdit({ ...edit, name: event.target.value })
                  }
                />
              </label>
              <label>
                가격 (원)
                <input
                  type="number"
                  min="0"
                  value={edit.price}
                  onChange={(event) =>
                    setEdit({ ...edit, price: Number(event.target.value) })
                  }
                />
              </label>
              <label>
                카테고리
                <select
                  value={edit.categoryId}
                  onChange={(event) =>
                    setEdit({ ...edit, categoryId: event.target.value })
                  }
                >
                  {dashboard?.store.categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                대표 이모지
                <input
                  value={edit.emoji}
                  onChange={(event) =>
                    setEdit({ ...edit, emoji: event.target.value })
                  }
                />
              </label>
              <label className="wide">
                메뉴 설명
                <textarea
                  value={edit.description}
                  onChange={(event) =>
                    setEdit({ ...edit, description: event.target.value })
                  }
                />
              </label>
              <label className="wide">
                재료 (쉼표로 구분)
                <input
                  value={edit.ingredients.join(", ")}
                  onChange={(event) =>
                    setEdit({
                      ...edit,
                      ingredients: event.target.value
                        .split(",")
                        .map((value) => value.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </label>
              <label>
                맵기
                <select
                  value={edit.spiceLevel}
                  onChange={(event) =>
                    setEdit({ ...edit, spiceLevel: Number(event.target.value) })
                  }
                >
                  {[0, 1, 2, 3, 4].map((value) => (
                    <option value={value} key={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                식사 조건 태그
                <input
                  value={edit.dietaryTags.join(", ")}
                  onChange={(event) =>
                    setEdit({
                      ...edit,
                      dietaryTags: event.target.value
                        .split(",")
                        .map((value) => value.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="vegan, no_pork"
                />
              </label>
            </div>
            <h3>알레르기 성분 확인</h3>
            <p className="fine-print">
              실제 재료와 제조 과정 확인 후 선택하세요. 미확인은 알레르기
              추천에서 제외됩니다.
            </p>
            <div className="allergen-editor">
              {ALLERGENS.map(([key, label]) => {
                const record = edit.allergens.find(
                  (entry) => entry.allergenKey === key,
                );
                return (
                  <label key={key}>
                    {label}
                    <select
                      value={record?.relation || "unknown"}
                      onChange={(event) =>
                        setEdit({
                          ...edit,
                          allergens: edit.allergens.map((entry) =>
                            entry.allergenKey === key
                              ? {
                                  ...entry,
                                  relation: event.target.value as
                                    "contains" | "excludes" | "unknown",
                                  verificationStatus:
                                    event.target.value === "unknown"
                                      ? "unknown"
                                      : "merchant_verified",
                                }
                              : entry,
                          ),
                        })
                      }
                    >
                      <option value="unknown">미확인</option>
                      <option value="contains">포함</option>
                      <option value="excludes">확인: 미포함</option>
                    </select>
                  </label>
                );
              })}
            </div>
            {edit.id && (
              <div className="option-editor">
                <h3>메뉴 옵션</h3>
                <p className="fine-print">
                  가격과 알레르기 정보는 각 선택지마다 확인해 주세요. 옵션 변경
                  시 기존 장바구니는 재확인이 필요합니다.
                </p>
                {dashboard?.menu
                  .find((item) => item.id === edit.id)
                  ?.options.map((group) => (
                    <div className="existing-option" key={group.id}>
                      <strong>{group.name}</strong>
                      <span>
                        {group.options
                          .map(
                            (option) =>
                              `${option.name} (+${money(option.priceDelta)})`,
                          )
                          .join(" · ")}
                      </span>
                      <button
                        className="button button-outline"
                        onClick={() => removeGroup(group.id)}
                      >
                        삭제
                      </button>
                    </div>
                  ))}
                <div className="new-option">
                  <strong>옵션 그룹 추가</strong>
                  <div className="option-fields">
                    <label>
                      그룹 이름
                      <input
                        value={optionDraft.name}
                        onChange={(event) =>
                          setOptionDraft({
                            ...optionDraft,
                            name: event.target.value,
                          })
                        }
                        placeholder="예: 토핑 선택"
                      />
                    </label>
                    <label>
                      최소 선택
                      <select
                        value={optionDraft.minSelect}
                        onChange={(event) =>
                          setOptionDraft({
                            ...optionDraft,
                            minSelect: Number(event.target.value),
                          })
                        }
                      >
                        {[0, 1, 2, 3, 4, 5].map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      최대 선택
                      <select
                        value={optionDraft.maxSelect}
                        onChange={(event) =>
                          setOptionDraft({
                            ...optionDraft,
                            maxSelect: Number(event.target.value),
                          })
                        }
                      >
                        {[1, 2, 3, 4, 5].map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {optionDraft.options.map((option, index) => (
                    <div className="option-draft-row" key={index}>
                      <div className="option-fields">
                        <label>
                          선택지 이름
                          <input
                            value={option.name}
                            onChange={(event) =>
                              updateOption(index, { name: event.target.value })
                            }
                            placeholder="예: 치즈 추가"
                          />
                        </label>
                        <label>
                          추가 금액
                          <input
                            type="number"
                            min="0"
                            value={option.priceDelta}
                            onChange={(event) =>
                              updateOption(index, {
                                priceDelta: Number(event.target.value),
                              })
                            }
                          />
                        </label>
                        <button
                          className="button button-outline"
                          onClick={() =>
                            setOptionDraft({
                              ...optionDraft,
                              options: optionDraft.options.filter(
                                (_, position) => position !== index,
                              ),
                            })
                          }
                          disabled={optionDraft.options.length === 1}
                        >
                          삭제
                        </button>
                      </div>
                      <label className="option-ingredients">
                        선택지 재료
                        <input
                          value={option.ingredients.join(", ")}
                          onChange={(event) =>
                            updateOption(index, {
                              ingredients: event.target.value
                                .split(",")
                                .map((value) => value.trim())
                                .filter(Boolean),
                            })
                          }
                          placeholder="쉼표로 구분"
                        />
                      </label>
                      <details>
                        <summary>선택지 알레르기 정보 확인</summary>
                        <div className="allergen-editor">
                          {ALLERGENS.map(([key, label]) => (
                            <label key={key}>
                              {label}
                              <select
                                value={
                                  option.allergens.find(
                                    (entry) => entry.allergenKey === key,
                                  )?.relation || "unknown"
                                }
                                onChange={(event) =>
                                  updateOptionAllergen(
                                    index,
                                    key,
                                    event.target.value as
                                      "contains" | "excludes" | "unknown",
                                  )
                                }
                              >
                                <option value="unknown">미확인</option>
                                <option value="contains">포함</option>
                                <option value="excludes">확인: 미포함</option>
                              </select>
                            </label>
                          ))}
                        </div>
                      </details>
                    </div>
                  ))}
                  <div className="option-editor-actions">
                    <button
                      className="button button-outline"
                      onClick={() =>
                        setOptionDraft({
                          ...optionDraft,
                          options: [...optionDraft.options, newOption()],
                        })
                      }
                      disabled={optionDraft.options.length >= 5}
                    >
                      <Plus size={16} /> 선택지 추가
                    </button>
                    <button
                      className="button button-primary"
                      onClick={addGroup}
                      disabled={
                        !optionDraft.name ||
                        optionDraft.options.some((option) => !option.name)
                      }
                    >
                      옵션 저장 <Check size={16} />
                    </button>
                  </div>
                </div>
              </div>
            )}
            <div className="editor-switches">
              <label>
                <input
                  type="checkbox"
                  checked={edit.isPublished}
                  onChange={(event) =>
                    setEdit({ ...edit, isPublished: event.target.checked })
                  }
                />
                손님에게 공개
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={edit.isAvailable}
                  onChange={(event) =>
                    setEdit({ ...edit, isAvailable: event.target.checked })
                  }
                />
                판매 가능
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={edit.isShareable}
                  onChange={(event) =>
                    setEdit({ ...edit, isShareable: event.target.checked })
                  }
                />
                함께 나눠 먹기
              </label>
            </div>
            <div className="editor-footer">
              <button
                className="button button-outline"
                onClick={() => setEdit(null)}
              >
                취소
              </button>
              <button
                className="button button-primary"
                disabled={busy || !edit.name || !edit.categoryId}
                onClick={saveMenu}
              >
                저장하기 <Check size={18} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
