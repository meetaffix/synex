import { test, expect } from "@playwright/test";

test("separate LinkedIn sign-in and publishing consent in the browser (mock provider)", async ({page}) => {
  await page.goto("/login");await page.getByRole("link",{name:"Continue with LinkedIn"}).click();
  await expect(page.locator("#scopes")).toHaveText("openid profile email");
  await page.getByRole("link",{name:"Approve test grant"}).click();
  await expect(page.getByRole("heading", { name: /^Good (morning|afternoon|evening)/, level: 1 })).toBeVisible();
  await page.goto("/others/publishing/connections");
  await page.getByRole("button",{name:"Connect LinkedIn",exact:true}).click();
  await expect(page.locator("#scopes")).toContainText("w_member_social");
  await page.getByRole("link",{name:"Approve test grant"}).click();
  await expect(page.getByText("Browser OIDC Fixture",{exact:true}).first()).toBeVisible();
  await page.reload();await expect(page.getByText("w_member_social",{exact:false}).first()).toBeVisible();
  await page.getByRole("button",{name:"Disconnect",exact:true}).click();
  await page.getByRole("dialog").getByRole("button",{name:"Disconnect",exact:true}).click();
  await expect(page.getByText("Reconnect required",{exact:true})).toBeVisible();
  await page.goto("/settings");await expect(page.getByRole("button",{name:"Unlink LinkedIn sign-in"})).toBeVisible();
});
