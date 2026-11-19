import { test, expect } from "@playwright/test";
import { callsTo, mockApi, newApi, post, publishingAccount } from "./mock-api";

/* Post review: invite a reviewer with a private link, see their answer, reply; the reviewer's own page. The API is mocked. */

const withPost = () => {
  const api = newApi();
  api.publishing = { posts: [post("p1", "Launch week")], accounts: [publishingAccount()], activity: [] };
  return api;
};

test("the owner creates a review link shown once, sees the feedback and an approval, replies, and can revoke the link", async ({ page }) => {
  const api = withPost();
  api.assistant.reviews.thread.push({ id: "f0", author: "Priya", decision: "approve", body: "", postVersion: 1, createdAt: "2026-11-16T09:00:00Z", fromReviewer: true });
  await mockApi(page, api);
  await page.goto("/others/publishing/studio?id=p1");
  const panel = page.getByRole("region", { name: "Reviewers" });
  await expect(panel.getByRole("button", { name: "Create review link" })).toBeDisabled();
  await panel.getByLabel("Reviewer name").fill("Mia");
  await panel.getByRole("button", { name: "Create review link" }).click();
  await expect(panel.getByText(/shown only once/)).toContainText("/review/TOKEN123");
  await expect(panel.getByText("Approved as it is now by Priya.")).toBeVisible();
  await expect(panel.getByRole("list", { name: "Review links" })).toContainText("Mia");
  await panel.getByLabel("Reply").fill("Thanks, publishing tomorrow");
  await panel.getByRole("button", { name: "Send reply" }).click();
  await expect(panel.getByRole("list", { name: "Feedback" })).toContainText("Thanks, publishing tomorrow");
  await panel.getByRole("button", { name: "Revoke" }).click();
  await expect(panel.getByRole("list", { name: "Review links" })).toContainText("revoked");
  expect(callsTo(api, "POST", /reviewers$/)[0].body).toEqual({ reviewer: "Mia" });
});

test("a reviewer with the link reads the post and approves or asks for changes, with no account", async ({ page }) => {
  const api = newApi({ signedOut: true });
  await mockApi(page, api);
  await page.goto("/review/TOKEN123");
  await expect(page.getByRole("heading", { name: "Launch week", level: 1 })).toBeVisible();
  await expect(page.getByRole("article", { name: "Post" })).toHaveText("We shipped it.");
  await expect(page.getByRole("button", { name: "Request changes" })).toBeDisabled(); // a change request needs words
  await page.getByLabel("Comment").fill("Make the first line shorter");
  await page.getByRole("button", { name: "Request changes" }).click();
  await expect(page.getByText("Thank you. Your request for changes was sent.")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Thank you. Your approval was sent.")).toBeVisible();
  const sent = callsTo(api, "POST", /\/review\/TOKEN123\/feedback$/).map((c) => (c.body as { decision: string }).decision);
  expect(sent).toEqual(["changes", "approve"]);
});

test("a link that does not work says what to do", async ({ page }) => {
  await mockApi(page, newApi({ signedOut: true }));
  await page.goto("/review/expired");
  await expect(page.getByRole("heading", { name: "This review link does not work" })).toBeVisible();
  await expect(page.getByText(/Ask the person who sent it for a new one/)).toBeVisible();
});
