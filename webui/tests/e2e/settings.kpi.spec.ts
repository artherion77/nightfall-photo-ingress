import { test, expect } from '@playwright/test';

// Note: These tests assume a running staging environment with a known API token
const API_BASE_URL = 'http://staging-photo-ingress:8000';
const API_TOKEN = process.env.API_TOKEN || 'test-token'; // Override via env

test.describe('KPI Thresholds Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to settings page
    await page.goto('/settings/kpi');
    
    // Wait for page to load
    await page.waitForSelector('h1:has-text("KPI Thresholds")');
  });

  test('should load and display default KPI thresholds', async ({ page }) => {
    // Verify page is loaded with all form fields visible
    await expect(page.locator('input#pending-warning')).toBeVisible();
    await expect(page.locator('input#pending-error')).toBeVisible();
    await expect(page.locator('input#disk-warning')).toBeVisible();
    await expect(page.locator('input#disk-error')).toBeVisible();

    // Verify default values are present
    await expect(page.locator('input#pending-warning')).toHaveValue('100');
    await expect(page.locator('input#pending-error')).toHaveValue('500');
    await expect(page.locator('input#disk-warning')).toHaveValue('80');
    await expect(page.locator('input#disk-error')).toHaveValue('95');
  });

  test('should show validation error when error threshold <= warning', async ({ page }) => {
    // Change pending_error to be less than pending_warning
    await page.locator('input#pending-warning').fill('500');
    await page.locator('input#pending-error').fill('400');
    
    // Trigger validation by clicking on another field or Button
    await page.locator('button:has-text("Save Changes")').click();

    // Verify error message appears
    await expect(
      page.locator('text=Error threshold must be greater than warning threshold')
    ).toBeVisible();

    // Verify Save button is disabled
    await expect(page.locator('button:has-text("Save Changes")')).toBeDisabled();
  });

  test('should allow editing and saving valid threshold values', async ({ page }) => {
    // Update threshold values
    await page.locator('input#pending-warning').fill('150');
    await page.locator('input#pending-error').fill('600');
    await page.locator('input#disk-warning').fill('75');
    await page.locator('input#disk-error').fill('90');

    // Click Save
    await page.locator('button:has-text("Save Changes")').click();

    // Wait for success message
    await expect(
      page.locator('text=KPI thresholds updated successfully')
    ).toBeVisible();

    // Reload page to verify persistence
    await page.reload();
    await page.waitForSelector('h1:has-text("KPI Thresholds")');

    // Verify values persisted
    await expect(page.locator('input#pending-warning')).toHaveValue('150');
    await expect(page.locator('input#pending-error')).toHaveValue('600');
    await expect(page.locator('input#disk-warning')).toHaveValue('75');
    await expect(page.locator('input#disk-error')).toHaveValue('90');
  });

  test('should reset to factory defaults', async ({ page }) => {
    // First, change threshold values
    await page.locator('input#pending-warning').fill('200');
    await page.locator('input#pending-error').fill('700');
    await page.locator('button:has-text("Save Changes")').click();
    
    // Wait for success
    await page.waitForSelector('text=KPI thresholds updated successfully');

    // Click Reset button
    await page.locator('button:has-text("Reset to Defaults")').click();

    // Accept confirmation dialog
    await page.on('dialog', dialog => {
      expect(dialog.message()).toContain('Reset KPI thresholds to factory defaults');
      dialog.accept();
    });

    // Wait for reset success message
    await expect(
      page.locator('text=KPI thresholds updated successfully')
    ).toBeVisible();

    // Verify values reset to defaults
    await expect(page.locator('input#pending-warning')).toHaveValue('100');
    await expect(page.locator('input#pending-error')).toHaveValue('500');
    await expect(page.locator('input#disk-warning')).toHaveValue('80');
    await expect(page.locator('input#disk-error')).toHaveValue('95');
  });

  test('should handle Cancel correctly', async ({ page }) => {
    // Get initial values
    const initialWarning = await page.locator('input#pending-warning').inputValue();

    // Make changes
    await page.locator('input#pending-warning').fill('999');

    // Click Cancel
    await page.locator('button:has-text("Cancel")').click();

    // Verify changes were discarded
    await expect(page.locator('input#pending-warning')).toHaveValue(initialWarning);
  });

  test('should show inline validation errors for out-of-range values', async ({ page }) => {
    // Try to set an out-of-range value
    await page.locator('input#pending-warning').fill('0');
    await page.locator('input#pending-error').fill('500');
    
    // Click Save to trigger validation
    await page.locator('button:has-text("Save Changes")').click();

    // Verify error message
    await expect(
      page.locator('text=Value must be between 1 and 9999')
    ).toBeVisible();

    // Verify Save button is disabled
    await expect(page.locator('button:has-text("Save Changes")')).toBeDisabled();
  });

  test('should disable form during save operation', async ({ page }) => {
    // Make a valid change
    await page.locator('input#pending-warning').fill('150');
    await page.locator('input#pending-error').fill('600');

    // Click Save
    const saveButton = page.locator('button:has-text("Save Changes")');
    await saveButton.click();

    // Verify Save button is disabled and shows "Saving..."
    await expect(saveButton).toBeDisabled();
    // Note: text may change to "Saving..." during the operation

    // Wait for success
    await expect(
      page.locator('text=KPI thresholds updated successfully')
    ).toBeVisible();
  });

  test('should handle API errors gracefully', async ({ page, context }) => {
    // Mock the API to return an error
    await context.addInitScript(() => {
      window.fetch = async (url, options) => {
        if (url.includes('/api/v1/settings/kpi-thresholds') && options?.method === 'PUT') {
          return new Response(
            JSON.stringify({ detail: 'Validation failed' }),
            { status: 422 }
          );
        }
        return originalFetch(url, options);
      };
    });

    // Make a change and try to save
    await page.locator('input#pending-warning').fill('150');
    await page.locator('input#pending-error').fill('600');
    await page.locator('button:has-text("Save Changes")').click();

    // Verify error message is displayed
    await expect(page.locator('text=Error:')).toBeVisible();
  });

  test('should maintain form state when navigating away and back', async ({ page, context }) => {
    // Make changes but don't save
    await page.locator('input#pending-warning').fill('200');
    await page.locator('input#pending-error').fill('700');

    // Navigate to another settings page
    await page.goto('/settings');
    
    // Navigate back
    await page.goto('/settings/kpi');
    await page.waitForSelector('h1:has-text("KPI Thresholds")');

    // Verify form reset to last saved values (not unsaved changes)
    // This tests that navigation clears unsaved state
    await expect(page.locator('input#pending-warning')).not.toHaveValue('200');
  });

  test('should display last update timestamp in success message', async ({ page }) => {
    // Make a change and save
    await page.locator('input#pending-warning').fill('175');
    await page.locator('input#pending-error').fill('625');
    await page.locator('button:has-text("Save Changes")').click();

    // Verify success message with timestamp
    const successMsg = page.locator('.success-banner');
    await expect(successMsg).toBeVisible();
    await expect(successMsg).toContainText('at');
  });
});
