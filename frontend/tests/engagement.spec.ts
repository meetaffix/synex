import { test, expect } from "@playwright/test";
import { account, callsTo, mockApi, newApi } from "./mock-api";

/* Manual engagement: react to a post or comment on it from a sender, by hand, with a history. The API is mocked; nothing reaches LinkedIn. */

const open = async (page: import("@playwright/test").Page) => {
  const api = newApi({ accounts: [account("a1", "Ada Lovelace"), account("a2", "Bo Sender")] });
  await mockApi(page, api);
  await page.goto("/others/publishing/engagement");
  await expect(page.getByRole("heading", { name: "React or comment" })).toBeVisible();
  return api;
};

test("a reaction and a comment are queued from the chosen sender, shown in the history, and a queued one can be cancelled", async ({ page }) => {
  const api = await open(page);
  await expect(page.getByRole("button", { name: "Queue" })).toBeDisabled();
  await page.getByLabel("React as").selectOption("a2");
  await page.getByLabel("Post address").fill("https://www.linkedin.com/feed/update/urn:li:activity:123/");
  await expect(page.getByRole("button", { name: "Queue" })).toBeDisabled(); // nothing chosen yet
  await page.getByLabel("Celebrate").check();
  await page.getByLabel("Comment (optional)").fill("Congratulations on the launch");
  await page.getByRole("button", { name: "Queue" }).click();
  await expect(page.getByText("Queued. The sender does it within its limits.")).toBeVisible();
  expect(callsTo(api, "POST", /^\/engagement$/)[0].body).toEqual({ accountId: "a2", postUrl: "https://www.linkedin.com/feed/update/urn:li:activity:123/", reaction: "celebrate", comment: "Congratulations on the launch" });
  const item = page.getByRole("list", { name: "Reactions and comments" }).getByRole("listitem").first();
  await expect(item).toContainText("Waiting for the sender");
  await expect(item).toContainText("Congratulations on the launch");
  await item.getByRole("button", { name: "Cancel" }).click();
  await expect(item).toContainText("Cancelled: Cancelled by you.");
});

test("an address that is not a LinkedIn post is refused with the reason, and the history starts empty", async ({ page }) => {
  await open(page);
  await expect(page.getByText("Nothing yet. Reactions and comments you queue appear here.")).toBeVisible();
  await page.getByLabel("Post address").fill("https://example.com/something");
  await page.getByLabel("Like").check();
  await page.getByRole("button", { name: "Queue" }).click();
  await expect(page.getByText(/Paste the address of one LinkedIn post/)).toBeVisible();
});

test("the comment counts its characters against the 1,250 limit", async ({ page }) => {
  await open(page);
  await page.getByLabel("Comment (optional)").fill("Hello");
  await expect(page.getByText("5 of 1250 characters.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Comment (optional)")).toHaveAttribute("maxlength", "1250");
});
