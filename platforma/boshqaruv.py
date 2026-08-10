# -*- coding: utf-8 -*-
"""Boshqaruv CLI — admin/ustoz akkauntlari, twin egaligi.

  python -m platforma.boshqaruv admin-yasa --login admin --parol XXX --ism "Admin"
  python -m platforma.boshqaruv rol --user 5 --rol egasi
  python -m platforma.boshqaruv parol --login admin --parol YANGI
  python -m platforma.boshqaruv twin-egasi --twin 2 --user 5
  python -m platforma.boshqaruv royxat
"""
import argparse

from . import auth, db, pg
from .sozlama import log


def admin_yasa(args):
    mavjud = db.user_login_ol(args.login)
    if mavjud:
        db.user_yangila(mavjud["id"], rol="admin",
                        parol_hash=auth.parol_hash(args.parol))
        log(f"mavjud user #{mavjud['id']} admin qilindi")
        return
    u = pg.bitta_d(
        "INSERT INTO userlar(ism, login, rol, parol_hash) VALUES(%s,%s,'admin',%s) "
        "RETURNING id, ism, login",
        args.ism, args.login.strip().lower(), auth.parol_hash(args.parol))
    log(f"admin yaratildi: #{u['id']} {u['ism']} (login: {u['login']})")


def rol(args):
    db.user_yangila(args.user, rol=args.rol)
    log(f"user #{args.user} roli: {args.rol}")


def parol(args):
    u = db.user_login_ol(args.login)
    if not u:
        raise SystemExit("bunday login yo'q")
    db.user_yangila(u["id"], parol_hash=auth.parol_hash(args.parol))
    log(f"parol yangilandi: {args.login}")


def twin_egasi(args):
    db.twin_yangila(args.twin, egasi_id=args.user)
    db.user_yangila(args.user, rol="egasi")
    log(f"twin #{args.twin} egasi: user #{args.user} (rol: egasi)")


def royxat(args):
    print("\n--- USERLAR ---")
    for u in db.userlar(limit=50):
        print(f"  #{u['id']:3d} {u['ism'][:22]:24s} rol={u['rol']:7s} "
              f"login={u['login'] or '-':14s} tg={u['tg_id'] or '-'}")
    print("\n--- TWINLAR ---")
    for t in db.twinlar(faqat_faol=False):
        print(f"  #{t['id']:3d} {t['nom'][:22]:24s} egasi={t['egasi_ism'] or '-':12s} "
              f"bo'lak={t['bolak_soni']}")


def main():
    p = argparse.ArgumentParser(description="Platforma boshqaruvi")
    s = p.add_subparsers(dest="buyruq", required=True)

    a = s.add_parser("admin-yasa"); a.set_defaults(fn=admin_yasa)
    a.add_argument("--login", required=True); a.add_argument("--parol", required=True)
    a.add_argument("--ism", default="Admin")

    a = s.add_parser("rol"); a.set_defaults(fn=rol)
    a.add_argument("--user", type=int, required=True)
    a.add_argument("--rol", choices=["client", "egasi", "admin"], required=True)

    a = s.add_parser("parol"); a.set_defaults(fn=parol)
    a.add_argument("--login", required=True); a.add_argument("--parol", required=True)

    a = s.add_parser("twin-egasi"); a.set_defaults(fn=twin_egasi)
    a.add_argument("--twin", type=int, required=True)
    a.add_argument("--user", type=int, required=True)

    a = s.add_parser("royxat"); a.set_defaults(fn=royxat)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
