import { createHmac } from 'node:crypto';

import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// Fixed UUIDs for idempotent upserts
const ADMIN_USER_ID = 'a1111111-1111-1111-1111-111111111111';
const ADMIN_ACCOUNT_ID = 'a2222222-2222-2222-2222-222222222222';
const DEMO_USER_ID = 'd1111111-1111-1111-1111-111111111111';
const DEMO_ACCOUNT_ID = 'd2222222-2222-2222-2222-222222222222';

// Must match TAG_ID_DEMO from libs/common/src/lib/config.ts
const TAG_ID_DEMO = 'efa08cb3-9b9d-4974-ac68-db13a19c4874';

const ACCESS_TOKEN_SALT = process.env.ACCESS_TOKEN_SALT;
const DEFAULT_ADMIN_TOKEN =
  process.env.DEFAULT_ADMIN_TOKEN || 'ghostfolio-admin-default-token';

/**
 * Replicates the HMAC-SHA512 logic from UserService.createAccessToken()
 */
function hashAccessToken(plainToken: string, salt: string): string {
  const hash = createHmac('sha512', salt);
  hash.update(plainToken);
  return hash.digest('hex');
}

async function main() {
  // --- Tags ---
  await prisma.tag.createMany({
    data: [
      {
        id: '4452656d-9fa4-4bd0-ba38-70492e31d180',
        name: 'EMERGENCY_FUND'
      },
      {
        id: 'f2e868af-8333-459f-b161-cbc6544c24bd',
        name: 'EXCLUDE_FROM_ANALYSIS'
      },
      {
        id: TAG_ID_DEMO,
        name: 'DEMO'
      }
    ],
    skipDuplicates: true
  });

  // --- Admin user ---
  if (!ACCESS_TOKEN_SALT) {
    console.warn(
      'WARNING: ACCESS_TOKEN_SALT is not set. Skipping admin/demo user seeding.'
    );
    return;
  }

  const hashedAdminToken = hashAccessToken(DEFAULT_ADMIN_TOKEN, ACCESS_TOKEN_SALT);

  await prisma.user.upsert({
    where: { id: ADMIN_USER_ID },
    create: {
      id: ADMIN_USER_ID,
      provider: 'ANONYMOUS',
      role: 'ADMIN',
      accessToken: hashedAdminToken
    },
    update: {
      accessToken: hashedAdminToken
    }
  });

  // --- Admin account ---
  await prisma.account.upsert({
    where: { id_userId: { id: ADMIN_ACCOUNT_ID, userId: ADMIN_USER_ID } },
    create: {
      id: ADMIN_ACCOUNT_ID,
      userId: ADMIN_USER_ID,
      currency: 'USD',
      name: 'My Account'
    },
    update: {}
  });

  // --- Admin settings ---
  await prisma.settings.upsert({
    where: { userId: ADMIN_USER_ID },
    create: {
      userId: ADMIN_USER_ID,
      settings: { currency: 'USD' }
    },
    update: {}
  });

  // --- Demo user ---
  await prisma.user.upsert({
    where: { id: DEMO_USER_ID },
    create: {
      id: DEMO_USER_ID,
      provider: 'ANONYMOUS',
      role: 'DEMO'
    },
    update: {}
  });

  // --- Demo account ---
  await prisma.account.upsert({
    where: { id_userId: { id: DEMO_ACCOUNT_ID, userId: DEMO_USER_ID } },
    create: {
      id: DEMO_ACCOUNT_ID,
      userId: DEMO_USER_ID,
      currency: 'USD',
      name: 'My Account'
    },
    update: {}
  });

  // --- Demo settings ---
  await prisma.settings.upsert({
    where: { userId: DEMO_USER_ID },
    create: {
      userId: DEMO_USER_ID,
      settings: { currency: 'USD' }
    },
    update: {}
  });

  // --- Demo properties (point demo login at admin user so instructors see agent portfolio) ---
  await prisma.property.upsert({
    where: { key: 'DEMO_USER_ID' },
    create: { key: 'DEMO_USER_ID', value: ADMIN_USER_ID },
    update: { value: ADMIN_USER_ID }
  });

  await prisma.property.upsert({
    where: { key: 'DEMO_ACCOUNT_ID' },
    create: { key: 'DEMO_ACCOUNT_ID', value: ADMIN_ACCOUNT_ID },
    update: { value: ADMIN_ACCOUNT_ID }
  });

  console.log('Seed completed successfully.');
  console.log(`Admin token: ${DEFAULT_ADMIN_TOKEN}`);
  console.log(
    'Use this token to log in as admin via the anonymous login flow.'
  );
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
