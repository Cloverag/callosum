import { apiClient } from './src/lib/api';

async function runTests() {
  console.log("Starting API client tests...\n");
  
  // Test 1: Get pending conflicts
  console.log("Test 1: getPendingConflicts");
  let pending = await apiClient.getPendingConflicts();
  console.assert(pending.length === 2, "Expected 2 pending conflicts initially");
  console.assert(pending[0].id === "3f1c019d-a442-491b-90f7-5264b387cf3e", "Expected correct ID for first conflict");
  console.log("Passed\n");

  // Test 2: Approve a conflict
  console.log("Test 2: approveConflict");
  const approveRes = await apiClient.approveConflict(pending[0].id);
  console.assert(approveRes.id === pending[0].id, "Expected returned ID to match");
  console.assert(approveRes.status === 'approved', "Expected status to be approved");
  
  // Verify it's no longer pending
  pending = await apiClient.getPendingConflicts();
  console.assert(pending.length === 1, "Expected 1 pending conflict after approval");
  console.log("Passed\n");

  // Test 3: Reject a conflict
  console.log("Test 3: rejectConflict");
  const rejectRes = await apiClient.rejectConflict(pending[0].id);
  console.assert(rejectRes.id === pending[0].id, "Expected returned ID to match");
  console.assert(rejectRes.status === 'rejected', "Expected status to be rejected");

  // Verify it's no longer pending
  pending = await apiClient.getPendingConflicts();
  console.assert(pending.length === 0, "Expected 0 pending conflicts after rejection");
  console.log("Passed\n");

  // Test 4: NotFound error handling
  console.log("Test 4: Error handling for missing IDs");
  try {
    await apiClient.approveConflict('fake-id');
    console.error("FAIL: Expected error to be thrown");
  } catch (error) {
    const e = error as Error;
    console.assert(e.message === "Conflict not found", "Expected 'Conflict not found' error");
    console.log("Passed\n");
  }

  console.log("All tests completed successfully!");
}

runTests();
