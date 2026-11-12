커스텀 로보 GX (GBA) 한글 패치 {ver}
제작: arqhive

「カスタムロボGX」(GBA, 일본판) 비공식 한국어 팬 패치입니다.
본편 대사, 선택지, 메뉴, 로보·파츠 설명, 도움말, 아이템 설명, 지도 장소 이름, 대회 정보,
타이틀 로고와 표·간판·창 머리글 그림 속 글자를 한글로 바꿉니다.


[준비물]

- 일본판 「カスタムロボGX」 롬 파일(ARJJ).
- BPS 패치를 적용하는 프로그램(Floating IPS, Rom Patcher JS 등).


[적용 방법]

1. 패치 프로그램에서 원본 롬과 ARJJ_KPatch_{ver}.bps 를 고릅니다.
2. 적용하면 한글판 롬이 만들어집니다.
3. 만들어진 롬의 해시가 아래 「패치 후」와 같은지 확인합니다.


[해시]

  패치 전(원본 롬)
    크기    {src_size} 바이트
    CRC32   {src_crc}
    MD5     {src_md5}
    SHA-256 {src_sha}

  패치 후({ver})
    크기    {dst_size} 바이트
    CRC32   {dst_crc}
    MD5     {dst_md5}
    SHA-256 {dst_sha}


[실행 환경]

- 확인함: 3DS open_agb_firm, mGBA.
- 3DS open_agb_firm 에서는 세이브 종류를 직접 정해 줘야 합니다.
  같이 든 CustomRoboGX_KO_{ver}.ini 를 한글판 롬과 같은 이름으로 바꿔
  /3ds/open_agb_firm/saves/ 폴더에 넣으세요(예: 롬이 CustomRoboGX_KO.gba 면 CustomRoboGX_KO.ini).
  ini 없이 실행하면 세이브가 제대로 되지 않을 수 있습니다.


[참고]

- 주인공 이름은 한글로 입력할 수 있습니다. 자음·모음을 차례로 고르면 글자가 조합됩니다(최대 7글자).
- 이름 뒤 조사(을/를, 이/가 등)는 이름 끝 글자의 받침에 맞춰 자동으로 바뀝니다.
- 칸이 좁은 곳은 띄어쓰기를 생략했습니다.
- 원래 영어로 나오는 글자는 영어로 두었습니다.
