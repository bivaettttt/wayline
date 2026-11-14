import { expect, test, type Page } from "@playwright/test";
const password = process.env.WAYLINE_DEMO_PASSWORD ?? "Wayline-local-demo";

async function signIn(page: Page, user: string) {
  await page.getByRole("textbox", { name: "Логин" }).fill(user);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible();
}
async function swap(page: Page, user: string) {
  await page.getByRole("button", { name: "Выйти" }).click();
  await signIn(page, user);
}
async function nav(page: Page, name: string) {
  await page
    .getByRole("navigation")
    .getByRole("link", { name, exact: true })
    .click();
}
async function capture(page: Page, name: string) {
  if (!process.env.WAYLINE_SHOTS) return;
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(3, 3);
  await page.screenshot({
    path: process.env.WAYLINE_SHOTS + "/" + name + ".png",
  });
}
async function choice(page: Page, label: string, prefix: string) {
  const field = page.getByRole("combobox", { name: label });
  const option = field.getByRole("option", { name: new RegExp("^" + prefix) });
  await expect(option).toHaveCount(1);
  await field.selectOption((await option.getAttribute("value")) ?? "");
}

test("traveler creates an itinerary and compares alternatives after a provider update", async ({
  page,
}) => {
  await page.goto("/");
  await signIn(page, "traveler");
  await page
    .getByRole("link", { name: "Новосибирск — Рим", exact: true })
    .first()
    .waitFor();
  await capture(page, "dashboard");
  await nav(page, "Поездки");
  await expect(
    page.getByRole("link", { name: "Новосибирск — Рим", exact: true }),
  ).toBeVisible();
  await capture(page, "trips");
  await page.getByRole("link", { name: "Создать поездку" }).click();
  const title = "Поездка в Рим · " + Date.now().toString().slice(-5);
  await page.getByRole("textbox", { name: "Название поездки" }).fill(title);
  await choice(page, "Сегмент 1", "WL101");
  await choice(page, "Сегмент 2", "WL202");
  await capture(page, "builder");
  await page.getByRole("button", { name: "Сохранить поездку" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "95 мин", exact: true }).first(),
  ).toBeVisible();
  await capture(page, "trip");
  const trip = page.url();
  await swap(page, "admin");
  await nav(page, "Лаборатория");
  await page.getByRole("combobox", { name: "Сценарий" }).selectOption("risk");
  await page.getByRole("button", { name: "Запустить сценарий" }).click();
  await expect(
    page.getByRole("heading", { name: "Проверка пройдена" }),
  ).toBeVisible();
  await capture(page, "lab");
  await nav(page, "Провайдер");
  await expect(
    page.getByText("Данные актуальны", { exact: true }),
  ).toBeVisible();
  await capture(page, "provider");
  await nav(page, "События");
  await expect(
    page.getByRole("cell", { name: "APPLIED", exact: true }).first(),
  ).toBeVisible();
  await capture(page, "events");
  await swap(page, "traveler");
  await nav(page, "Уведомления");
  const notice = page
    .getByRole("row")
    .filter({ hasText: title })
    .filter({ hasText: "Недостаточный запас пересадки" })
    .first();
  await expect(notice).toBeVisible();
  await capture(page, "notifications");
  await notice.getByRole("button", { name: "Отметить прочитанным" }).click();
  await expect(notice.getByText("Прочитано")).toBeVisible();
  await page.evaluate((url) => (location.hash = new URL(url).hash), trip);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await capture(page, "connection");
  await capture(page, "disruption-details");
  await page.getByRole("button", { name: "Найти альтернативы" }).click();
  await expect(
    page.getByRole("heading", { name: "Сравнение маршрутов" }),
  ).toBeVisible();
  await expect(page.getByText("Подходящие варианты найдены")).toBeVisible();
  await capture(page, "alternatives");
  await page
    .getByRole("heading", { name: "Сравнение маршрутов" })
    .scrollIntoViewIfNeeded();
  await capture(page, "comparison");
  await nav(page, "Рейсы");
  await page.getByRole("link", { name: "WL101", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "История рейса" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "APPLIED", exact: true }).first(),
  ).toBeVisible();
  await capture(page, "flight");
});

test("disruption centre only exposes owned incidents", async ({ page }) => {
  await page.goto("/");
  await signIn(page, "admin");
  await nav(page, "Лаборатория");
  await page.getByRole("combobox", { name: "Сценарий" }).selectOption("cancel");
  await page.getByRole("button", { name: "Запустить сценарий" }).click();
  await expect(
    page.getByRole("heading", { name: "Проверка пройдена" }),
  ).toBeVisible();
  await swap(page, "traveler");
  await nav(page, "Нарушения");
  const link = page
    .getByRole("link", { name: "Lab · Отмена рейса", exact: true })
    .first();
  await expect(link).toBeVisible();
  await capture(page, "disruptions");
  await link.click();
  await expect(
    page.getByRole("cell", { name: "Отмена или перенаправление" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ознакомлен" }).click();
  await expect(
    page.getByText("Принято к сведению", { exact: true }),
  ).toBeVisible();
  await capture(page, "disruption-details");
  await swap(page, "other");
  await expect(page.getByRole("alert")).toContainText("TRIP_NOT_FOUND");
});
