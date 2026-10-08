
void FUN_00422c40(void)

{
  bool bVar1;
  undefined *puVar2;
  undefined4 *puVar3;
  uint uVar4;
  short *psVar5;
  int in_stack_00000068;
  undefined1 auStack_9d8 [4];
  undefined4 uStack_9d4;
  undefined1 auStack_9c0 [4];
  undefined4 uStack_9bc;
  int iVar6;
  size_t sVar7;
  undefined1 auStack_9a4 [4];
  undefined4 uStack_9a0;
  undefined4 uStack_998;
  undefined1 auStack_98c [16];
  undefined4 uStack_97c;
  undefined4 local_8f0;
  undefined4 local_8ec;
  undefined4 *local_8e8;
  undefined4 local_8e4;
  undefined4 local_8e0;
  undefined1 *local_8dc;
  int local_8d8;
  short *local_8d4;
  uint local_8d0;
  short *local_8cc;
  undefined4 local_8c8;
  void *local_8c4;
  void *local_8c0;
  short *local_8bc;
  int local_8b8;
  HWND local_8b4;
  short *local_8b0;
  short *local_8ac;
  char *local_8a8;
  char *local_8a4;
  short local_8a0;
  short local_89c;
  short local_89a;
  short *local_898;
  char *local_894;
  char *local_890;
  undefined4 *local_88c;
  short *local_888;
  short *local_884;
  char *local_880;
  int *local_87c;
  char *local_878;
  int *local_874;
  int *local_870;
  short *local_86c;
  short *local_868;
  short local_864;
  short local_862;
  short local_860;
  char local_85d;
  int *local_85c;
  char local_858;
  char local_857;
  char local_856;
  char local_855;
  undefined4 local_854;
  short local_850 [256];
  undefined1 local_650 [4];
  short local_64c [256];
  function<void___cdecl(void)> local_44c [384];
  int local_2cc;
  undefined1 local_2c8 [28];
  function<void___cdecl(void)> local_2ac [24];
  function<void___cdecl(void)> local_294 [24];
  function<void___cdecl(void)> local_27c [24];
  function<void___cdecl(void)> local_264 [24];
  function<void___cdecl(void)> local_24c [24];
  function<void___cdecl(void)> local_234 [24];
  WCHAR local_21c [260];
  uint local_14;
  void *local_10;
  undefined1 *puStack_c;
  int local_8;
  
  puStack_c = &LAB_00474db1;
  local_10 = ExceptionList;
  local_14 = DAT_0048d304 ^ (uint)&stack0xfffffffc;
  ExceptionList = &local_10;
  local_8 = 4;
  puVar2 = FUN_00410480();
  FUN_00410cd0((uint *)(puVar2 + 0xac));
  puVar3 = (undefined4 *)FUN_00410480();
  *puVar3 = 0;
  puVar3[1] = 0;
  puVar2 = FUN_00410480();
  puVar2[0xa8] = 1;
  local_8a4 = (char *)FUN_00418990(&stack0x00000034);
  puVar2 = FUN_00410480();
  local_878 = puVar2 + 8;
  do {
    local_855 = *local_8a4;
    *local_878 = local_855;
    local_8a4 = local_8a4 + 1;
    local_878 = local_878 + 1;
  } while (local_855 != '\0');
  local_8a8 = (char *)FUN_00418990(&stack0x0000004c);
  puVar2 = FUN_00410480();
  local_880 = puVar2 + 0x58;
  do {
    local_856 = *local_8a8;
    *local_880 = local_856;
    local_8a8 = local_8a8 + 1;
    local_880 = local_880 + 1;
  } while (local_856 != '\0');
  puVar2 = FUN_00410480();
  uStack_97c = 0x422d8a;
  QueryPerformanceFrequency((LARGE_INTEGER *)(puVar2 + 0xc0));
  puVar2 = FUN_00410480();
  uStack_97c = 0x422d9b;
  QueryPerformanceCounter((LARGE_INTEGER *)(puVar2 + 0xb8));
  puVar2 = FUN_00410480();
  *(int *)(puVar2 + 200) = in_stack_00000068;
  puVar2 = FUN_00410480();
  FUN_00410330((uint *)(puVar2 + 0xac));
  FUN_00423740((int)local_44c);
  local_8._0_1_ = 5;
  FUN_00420620(auStack_98c,"recv begin...");
  local_8._0_1_ = 6;
  FUN_00420620(auStack_9a4,"info");
  local_8._0_1_ = 5;
  FUN_0041bc70();
  uStack_998 = 0x422e22;
  FUN_0041d630(&stack0xfffff670,&stack0x0000004c);
  local_8._0_1_ = 7;
  FUN_00410ed0(&stack0xfffff658,&stack0x00000004);
  local_8._0_1_ = 5;
  FUN_0043b800(local_44c);
  FUN_00420620(auStack_9c0,"recv end...");
  local_8._0_1_ = 8;
  FUN_00420620(auStack_9d8,"info");
  local_8._0_1_ = 5;
  FUN_0041bc70();
  if (local_2cc == 3) {
    FUN_00422690((basic_string<char,std::char_traits<char>,std::allocator<char>_> *)&stack0x0000006c
                );
    FUN_00410ed0(auStack_9c0,&stack0x0000006c);
    local_85d = FUN_004229f0();
    if (local_85d == '\0') {
      memset(local_21c,0,0x208);
      GetEnvironmentVariableW(L"USERPROFILE",local_21c,0x104);
      FUN_00420f70(local_24c,local_21c);
      local_8._0_1_ = 9;
      FUN_00420f70(auStack_9c0,L"Desktop");
      FUN_00422840(local_24c);
      FID_conflict_operator_(&stack0x0000006c,local_24c);
      local_8._0_1_ = 5;
      std::function<void___cdecl(void)>::~function<void___cdecl(void)>(local_24c);
    }
    FUN_00410ed0(auStack_9c0,&stack0x0000001c);
    FUN_00422840(&stack0x00000004);
    FUN_0041bdb0(&stack0x0000006c);
    FUN_0041bdb0(&stack0x00000004);
    uStack_9d4 = 0x422fa6;
    FUN_00435070(auStack_9c0,L"Copy \"%s\" To \"%s\"");
    local_8._0_1_ = 10;
    FUN_00420620(auStack_9d8,"info");
    local_8._0_1_ = 5;
    FUN_00410f70();
    FUN_00410ed0(auStack_9c0,&stack0x0000006c);
    local_8._0_1_ = 0xb;
    FUN_00410ed0(auStack_9d8,&stack0x00000004);
    local_8._0_1_ = 5;
    FUN_00422080(local_234);
    local_8._0_1_ = 0xc;
    local_8b4 = FindWindowW((LPCWSTR)0x0,L"UIStudentMainWnd");
    if ((DAT_0048fa88 == '\0') && (local_8b4 != (HWND)0x0)) {
      bVar1 = FUN_0041f900(local_234);
      if (bVar1) {
        FUN_004351a0(&stack0x0000006c,L"\\");
        memset(local_850,0,0x200);
        FUN_00435960(local_264,&stack0x0000006c,&stack0x0000001c);
        uVar4 = FID_conflict_size(local_264);
        if (uVar4 < 0x100) {
          local_8ac = (short *)FUN_0041bdb0(local_264);
          local_884 = local_850;
          do {
            local_860 = *local_8ac;
            *local_884 = local_860;
            local_8ac = local_8ac + 1;
            local_884 = local_884 + 1;
          } while (local_860 != 0);
          local_854 = 1;
          local_8f0 = 0;
          local_8e8 = &local_854;
          local_8ec = 0x204;
          uStack_9bc = 0x423175;
          SendMessageW(local_8b4,0x4a,0,(LPARAM)&local_8f0);
        }
        std::function<void___cdecl(void)>::~function<void___cdecl(void)>(local_264);
      }
      else {
        FUN_0041bdb0(local_234);
        FUN_00435070(auStack_9c0,L"Result:\"%s\"");
        local_8._0_1_ = 0xd;
        FUN_00420620(auStack_9d8,"info");
        local_8._0_1_ = 0xc;
        FUN_00410f70();
        FUN_00429310(local_27c,local_234);
        local_8 = CONCAT31(local_8._1_3_,0xe);
        FUN_004351a0(&stack0x0000006c,L"\\");
        memset(local_64c,0,0x200);
        local_8b0 = (short *)FUN_0041bdb0(&stack0x0000006c);
        local_888 = local_64c;
        do {
          local_862 = *local_8b0;
          *local_888 = local_862;
          local_8b0 = local_8b0 + 1;
          local_888 = local_888 + 1;
        } while (local_862 != 0);
        local_8c4 = (void *)FUN_00442fc0(local_27c,(undefined4 *)local_2ac);
        local_8._0_1_ = 0xf;
        local_8c0 = local_8c4;
        local_8c8 = FUN_004371d0(local_8c4,local_294);
        local_8cc = (short *)FUN_0041bdb0(local_8c8);
        local_868 = local_8cc;
        do {
          local_8a0 = *local_868;
          local_868 = local_868 + 1;
        } while (local_8a0 != 0);
        local_8d0 = (int)local_868 - (int)local_8cc;
        local_88c = (undefined4 *)(local_650 + 2);
        do {
          local_89a = *(short *)((int)local_88c + 2);
          local_88c = (undefined4 *)((int)local_88c + 2);
        } while (local_89a != 0);
        psVar5 = local_8cc;
        puVar3 = local_88c;
        for (uVar4 = local_8d0 >> 2; uVar4 != 0; uVar4 = uVar4 - 1) {
          *puVar3 = *(undefined4 *)psVar5;
          psVar5 = psVar5 + 2;
          puVar3 = puVar3 + 1;
        }
        for (uVar4 = local_8d0 & 3; uVar4 != 0; uVar4 = uVar4 - 1) {
          *(char *)puVar3 = (char)*psVar5;
          psVar5 = (short *)((int)psVar5 + 1);
          puVar3 = (undefined4 *)((int)puVar3 + 1);
        }
        local_8bc = local_8cc;
        std::function<void___cdecl(void)>::~function<void___cdecl(void)>(local_294);
        local_8._0_1_ = 0xe;
        FUN_0040f620(local_2ac);
        local_650 = (undefined1  [4])0x1;
        local_8e4 = 0;
        local_8dc = local_650;
        local_8e0 = 0x204;
        uStack_9bc = 0x4233cf;
        SendMessageW(local_8b4,0x4a,0,(LPARAM)&local_8e4);
        local_8._0_1_ = 0xc;
        FUN_0040f620(local_27c);
      }
    }
    local_8._0_1_ = 5;
    std::function<void___cdecl(void)>::~function<void___cdecl(void)>(local_234);
  }
  else {
    FUN_00410ed0(auStack_9c0,&stack0x00000004);
    FUN_00421960();
  }
  local_86c = (short *)FUN_0041bdb0(&stack0x00000004);
  local_8d4 = local_86c + 1;
  do {
    local_89c = *local_86c;
    local_86c = local_86c + 1;
  } while (local_89c != 0);
  local_8d8 = (int)local_86c - (int)local_8d4 >> 1;
  local_8b8 = local_8d8 * 2 + 2;
  local_85c = malloc(local_8d8 * 2 + 0x462);
  if (local_85c != (int *)0x0) {
    memset(local_85c,0,local_8b8 + 0x460);
    *local_85c = local_8b8 + 0x45c;
    local_85c[1] = 5;
    local_85c[2] = local_2cc;
    local_85c[0x117] = in_stack_00000068;
    local_890 = (char *)FUN_00418990(local_2c8);
    local_870 = local_85c + 3;
    do {
      local_857 = *local_890;
      *(char *)local_870 = local_857;
      local_890 = local_890 + 1;
      local_870 = (int *)((int)local_870 + 1);
    } while (local_857 != '\0');
    local_894 = (char *)FUN_00418990(&stack0x00000034);
    local_87c = local_85c + 0x103;
    do {
      local_858 = *local_894;
      *(char *)local_87c = local_858;
      local_894 = local_894 + 1;
      local_87c = (int *)((int)local_87c + 1);
    } while (local_858 != '\0');
    local_898 = (short *)FUN_0041bdb0(&stack0x00000004);
    local_874 = local_85c + 0x118;
    do {
      local_864 = *local_898;
      *(short *)local_874 = local_864;
      local_898 = local_898 + 1;
      local_874 = (int *)((int)local_874 + 2);
    } while (local_864 != 0);
    FUN_004066e0(&DAT_0048fae4,(char **)&local_85c);
  }
  puVar2 = FUN_00410480();
  FUN_00410cd0((uint *)(puVar2 + 0xac));
  puVar2 = FUN_00410480();
  puVar2[0xa8] = 0;
  puVar3 = (undefined4 *)FUN_00410480();
  *puVar3 = 0;
  puVar3[1] = 0;
  sVar7 = 0x50;
  iVar6 = 0;
  puVar2 = FUN_00410480();
  memset(puVar2 + 8,iVar6,sVar7);
  sVar7 = 0x50;
  iVar6 = 0;
  puVar2 = FUN_00410480();
  memset(puVar2 + 0x58,iVar6,sVar7);
  puVar2 = FUN_00410480();
  *(undefined4 *)(puVar2 + 200) = 0xffffffff;
  puVar2 = FUN_00410480();
  FUN_00410330((uint *)(puVar2 + 0xac));
  local_8._0_1_ = 4;
  FUN_00423770(local_44c);
  local_8._0_1_ = 3;
  std::function<void___cdecl(void)>::~function<void___cdecl(void)>
            ((function<void___cdecl(void)> *)&stack0x00000004);
  local_8._0_1_ = 2;
  std::function<void___cdecl(void)>::~function<void___cdecl(void)>
            ((function<void___cdecl(void)> *)&stack0x0000001c);
  local_8._0_1_ = 1;
  std::function<void___cdecl(void)>::~function<void___cdecl(void)>
            ((function<void___cdecl(void)> *)&stack0x00000034);
  local_8 = (uint)local_8._1_3_ << 8;
  std::function<void___cdecl(void)>::~function<void___cdecl(void)>
            ((function<void___cdecl(void)> *)&stack0x0000004c);
  local_8 = 0xffffffff;
  std::function<void___cdecl(void)>::~function<void___cdecl(void)>
            ((function<void___cdecl(void)> *)&stack0x0000006c);
  ExceptionList = local_10;
  uStack_9a0 = 0x423734;
  __security_check_cookie(local_14 ^ (uint)&stack0xfffffffc);
  return;
}

